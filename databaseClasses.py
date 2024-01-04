#Library imports
import boto3
import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
import urllib3
import random
import time
import os
import mimetypes
import requests
import hashlib
import base64

#Module imports
from dotenv import load_dotenv
from dataclasses import dataclass
from io import BytesIO
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor,as_completed
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AWSS3Connection():
    bucket_name = os.environ.get("AWSBUCKETNAME")
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=os.environ.get("AWSACCESSKEYID"),
            aws_secret_access_key=os.environ.get("AWSSECRETKEY"),
            region_name=os.environ.get("AWSREGION"),
            endpoint_url='https://s3.us-east-2.amazonaws.com',
        )

    @staticmethod
    def initialize_s3():
        return boto3.client(
            's3',
            aws_access_key_id=os.environ.get("AWSACCESSKEYID"),
            aws_secret_access_key=os.environ.get("AWSSECRETKEY"),
            region_name=os.environ.get("AWSREGION"),
            endpoint_url='https://s3.us-east-2.amazonaws.com',
        )
    
    @staticmethod
    def make_valid_url(url):
        if url.startswith("//"):
            return "http:" + url
        elif url.startswith("/"):
            return "http:/" + url
        else:
            return url
        
    @staticmethod
    def get_s3_key_from_url(url):
        valid_url = AWSS3Connection.make_valid_url(url)  # Make sure the URL is valid
        url_encoded = base64.b64encode(valid_url.encode('utf-8'))  # Encode the valid URL
        s3_key = hashlib.sha256(url_encoded).hexdigest()  # Hash the encoded URL
        return s3_key
        
    @staticmethod
    def list_all_objects(s3_client, bucket_name):
        """List all objects in an S3 bucket."""
        continuation_token = None
        files = set()

        while True:
            # Add the continuation token to the call if we received one from the previous call
            list_kwargs = dict(Bucket=bucket_name)
            if continuation_token:
                list_kwargs['ContinuationToken'] = continuation_token

            response = s3_client.list_objects_v2(**list_kwargs)

            # Extend the files set with the new page of objects
            if 'Contents' in response:
                for file in response['Contents']:
                    file_key = file['Key']
                    files.add(file_key)

            # Check if the response is truncated, if so, set the token for the next page
            if response.get('IsTruncated'):  # Check if there are more pages
                continuation_token = response.get('NextContinuationToken')
            else:
                break  # No more pages, break the loop

        return files
    

    def download_and_upload_image(self, url, session, scraper):
        try:
            image_bytes_io = self.download_image(url, session, scraper)
            if image_bytes_io:
                self.upload_to_s3(image_bytes_io, url, url)
            else:
                print(f"Failed to download {url}")
        except Exception as e:
            print(f"Exception during processing {url}: {e}")

        
    def download_image(self, url, sess, scraper):
        count = 0
        proxy = scraper.datacenter_proxy()
        sess.proxies.update(proxy)
        while count < 5:
            try:
                response = sess.get(url)
                if response.status_code == 200:
                    return BytesIO(response.content)
            except Exception as e:
                print(f"Error downloading image {url}: {e}")
            
            time.sleep(5)  # Wait before retrying
            new_proxy = scraper.firefox_proxy()
            sess.proxies.update(new_proxy)
            count += 1
    
        print("Giving up on url", url)
        return None

    def upload_to_s3(self, image_bytes_io, s3_filename, original_url):
        mime_type, _ = mimetypes.guess_type(original_url)
        if mime_type is None:
            mime_type = 'image/jpeg'

        try:
            s3_filename_encoded = base64.b64encode(s3_filename.encode('utf-8'))
            s3_key = hashlib.sha256(s3_filename_encoded).hexdigest()
            self.s3.put_object(
                Bucket=AWSS3Connection.bucket_name,
                Key=s3_key,
                Body=image_bytes_io.getvalue(),
                ContentType=mime_type
            )
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            raise

    def process_batch(self, urls, session, scraper):
        proxy = scraper.datacenter_proxy()
        session.proxies.update(proxy)
        for url in urls:
            try:
                full_url = self.make_valid_url(url)
                image_bytes_io = self.download_image(full_url, session, scraper)
                if image_bytes_io:
                    self.upload_to_s3(image_bytes_io, full_url, full_url)
                else:
                    print(f"Failed to download {url}")
            except Exception as e:
                print(f"Exception during processing {url}: {e}")
                

    def process_url_images(self, urls_chunk, scraper):
        print('Processing URLs...')
        batch_size = 5
        num_batches = len(urls_chunk) // batch_size + (len(urls_chunk) % batch_size > 0)
        with ThreadPoolExecutor(max_workers=20) as executor:  # Adjust the number of workers as needed
            session = requests.Session()
            retry_strategy = Retry(
            total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["HEAD", "GET", "OPTIONS"],
                backoff_factor=1
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session = requests.Session()
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            batches = [urls_chunk[i:i + batch_size] for i in range(0, len(urls_chunk), batch_size)]
        
            # Each thread processes a batch of URLs
            futures = [executor.submit(self.process_batch, batch, session, scraper) for batch in batches]



            with tqdm(total=num_batches, desc="Batches completed", unit="batch") as pbar:
                for future in as_completed(futures):
                    batch_result = future.result()  # This will raise exceptions from the threads, if any
                    pbar.update(1)  # Update the progress bar for each completed batch


    def parse_image_urls(rows):
        image_urls, main_image_queue, other_image_queue = [], [], []
        urls = rows[:, 1]

        for url in urls:
            split_urls = url[1:-1].split("|" if "|" in url else ",")
            split_urls = split_urls[0::3]
            best_image_url = split_urls[-3] if len(split_urls) >= 3 else (split_urls[-2] if len(split_urls) >= 2 else split_urls[-1])
            
            other_images = [u for u in split_urls if u != best_image_url]
            main_image_queue.append(best_image_url)
            other_image_queue.extend(other_images)

        return main_image_queue, other_image_queue

    def filter_new_images(files, image_queue, get_s3_key):
        new_images = [url for url in image_queue if get_s3_key(url) not in files]
        return new_images

    def upload_images_to_s3(self, company, scraper, upload_to_rds=False):
        query = f"""SELECT url, images
                    FROM productdata
                    WHERE company = '{company}'
                    ORDER BY unique_ids ASC;"""

        rows = scraper.pg.run_query(query)
        files = self.list_all_objects(self.s3, self.bucket_name)
        print(f"{len(files)} images already in S3.")

        rows = np.array(rows)
        main_image_queue, other_image_queue = self.parse_image_urls(rows)
        main_new_images = self.filter_new_images(files, main_image_queue, self.get_s3_key_from_url)
        other_new_images = self.filter_new_images(files, other_image_queue, self.get_s3_key_from_url)

        image_urls = main_new_images + other_new_images
        print(f"{len(image_urls)} images to be added to S3.")

        self.process_url_images(image_urls, scraper)


@dataclass
class Column(): 
    name: str
    type: str
    isNull: bool
    isPrimary: bool
    

class PostgressDBConnection():
    def __init__(self, table_name = "productdata", isAWS = True, autocommit = False):
        """Initialize the connection to the PostgressSQL database. Make an bject for this for every table you want to connect to, so the logic stays intact. Database can take up to 20 connections at once at the moment."""
        if isAWS:
            self.conn = psycopg2.connect(
                dbname=os.environ.get("AWSDBNAME"),
                user=os.environ.get("AWSDBUSER"),
                password=os.environ.get("AWSDBPASSWORD"),
                host=os.environ.get("AWSDBURL"),
                port=os.environ.get("AWSDBPORT"),
                sslmode='require',
            )
        else:
            self.conn = psycopg2.connect(
                dbname=os.environ.get("DATABASENAME"),
                user=os.environ.get("DATABASEUSER"),
                password=os.environ.get("DATABASEPASSWORD"),
                host=os.environ.get("DATABASEURL"),
                port=os.environ.get("DATABASEPORT")
            )
        if autocommit:
            self.conn.autocommit = True
        self.table_name = table_name

    def create_product_table(self, tablename=None):
        """Columns are the following:
            columns = ['unique_ids', 'name', 'gender', 'color', 'description', 'compositions', 'price', 'sizes', 'images', 'url', 'company', 'timestamp']
        """
        # Create table using self.pg.conn. Just hardcode the above column value, unique_ids being the key of table.
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {"productdata" if not(tablename) else tablename} (
            unique_ids serial PRIMARY KEY,
            name TEXT,
            gender TEXT,
            color TEXT,
            description TEXT,
            compositions TEXT,
            price TEXT,
            sizes TEXT,
            images TEXT,
            url TEXT UNIQUE,
            company TEXT,
            timestamp TEXT
        );"""

        try:
            # Create a cursor object and execute the SQL statement
            cursor = self.conn.cursor()
            cursor.execute(create_table_sql)
            # Commit the changes to the database
            self.conn.commit()
            if tablename:
                print(f"Table '{tablename}' created or already exists.")
            else:
                print("Table 'productdata' created or already exists.")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error: {error}")
        finally:
            # Close the cursor and the database connection
            cursor.close()
    
    def create_company_product_table(self, tablename):
        self.create_product_table(tablename)
        
    def create_product_urls_table(self, tablename = "producturls"):
        """ Create new table, with fields url and company"""
        sql_query = f"""
        CREATE TABLE IF NOT EXISTS {tablename} (
            unique_ids serial PRIMARY KEY,
            url TEXT UNIQUE,
            company TEXT,
            timestamp TEXT
        );"""

        try:
            # Create a cursor object and execute the SQL statement
            cursor = self.conn.cursor()
            cursor.execute(sql_query)
            # Commit the changes to the database
            self.conn.commit()
            print("Table created or already exists.")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error: {error}")

    
    def create_table(self, table_name:str, columns:Column):
        """Create a table in the database with the given name, columns. Column is an object itself, with the attributes name, type, isNull, and isPrimary."""
        #Check if table exists first.
        if self.table_exists(table_name):
            print("Table already exists")
            return
        query = (f"CREATE TABLE IF NOT EXISTS {table_name} ("
                + ','.join([f"{column.name} {column.type} {'NOT NULL' if not column.isNull else ''} "
                            f"{'PRIMARY KEY' if column.isPrimary else ''}" for column in columns]) + ');')
        try: 
            curr = self.conn.cursor()
            curr.execute(query)
            self.conn.commit()
            self.table_name = table_name
        except:
            self.conn.rollback()
            raise Exception("Error creating table")
        
    def remove_url_duplicates(self, company, tablename = "producturls"):
        """Remove duplicates in the database, based on the url. Remove only for given company (to keep it safe/shorter runtime)"""
        tablename = f"producturls_{company}"
        query = f"""DELETE FROM {tablename} 
                    WHERE unique_ids NOT IN (
                        SELECT MIN(unique_ids) 
                        FROM {tablename} 
                        WHERE company = '{company}' 
                        GROUP BY url
                    );"""
        try:
            curr = self.conn.cursor()
            curr.execute(query)
            self.conn.commit()

        except:
            self.conn.rollback()
            raise Exception("Error removing duplicates from database")
        

    def remove_product_duplicates(self, company, tablename = "productdata"):
        """Remove duplicates in the database, based on the url. Remove only for given company (to keep it safe/shorter runtime)"""
        tablename = f"productdata_{company}"
        query = f"""DELETE FROM {tablename} 
                    WHERE unique_ids NOT IN (
                        SELECT MIN(unique_ids) 
                        FROM {tablename} 
                        WHERE company = '{company}' 
                        GROUP BY url
                    );"""
        try:
            curr = self.conn.cursor()
            curr.execute(query)
            self.conn.commit()
        except:
            self.conn.rollback()
            raise Exception("Error removing duplicates from database")
        
        # Now, remove duplicates from the total database as well. 
        query = f"""DELETE FROM productdata
                    WHERE unique_ids NOT IN (
                        SELECT MIN(unique_ids) 
                        FROM productdata 
                        WHERE company = '{company}' 
                        GROUP BY url
                    );"""
        try:
            curr = self.conn.cursor()
            curr.execute(query)
            self.conn.commit()
        except:
            self.conn.rollback()
            raise Exception("Error removing duplicates from database")
     
         
    def table_exists(self, table_name):
        """
        Check if a table exists in the current database connection.
        
        Args:
        - connection: psycopg2 connection object
        - table_name: the name of the table to check

        Returns:
        - True if table exists, False otherwise
        """
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE tablename = %s
                );
            """, (table_name,))
            
            return cursor.fetchone()[0]

    def run_query(self, query, tablename = None):
        """Runs a query for the database table selected."""
        try:
            curr = self.conn.cursor()
            curr.execute(query)
            print(query)
            rows = curr.fetchall()
            rows = np.array(rows)
            return rows
        except Exception as e:
            print("Error running query")
            print(e)
            self.conn.rollback()
        

    def test_connection(self):
        """Test the connection to the database."""
        try:
            curr = self.conn.cursor()
            curr.execute("SELECT version();")
            rows = curr.fetchall()
            self.conn.commit()
            return True
        except Exception as e:
            print("Error testing connection")
            self.conn.rollback()
            return False

        
    def save_data_to_db(self, tablename, data, columns): 
        if not(self.table_exists("productdata")):
            self.create_product_table()      

        if not(self.table_exists(tablename)):
            self.create_company_product_table(tablename)

        if not(data):
            print("No data provided")
            return
        
        if not(columns):
            print("No columns provided")
            return
        
        insert_query = f"INSERT INTO {tablename} ({','.join([column for column in columns])}) VALUES %s ON CONFLICT (url) DO UPDATE SET timestamp = EXCLUDED.timestamp;"
        new_data = []
        for row in data:
            if type(row) == list:
                new_data.append(tuple(row))
            else:
                continue
        with self.conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, insert_query, new_data)
        self.conn.commit()

        # Now, commit into the total database as well.
        insert_query = f"INSERT INTO productdata ({','.join([column for column in columns])}) VALUES %s ON CONFLICT (url) DO UPDATE SET timestamp = EXCLUDED.timestamp;"
        with self.conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, insert_query, new_data)
        self.conn.commit()


    def save_urls_db(self, url_list, company_name):
        if (not(url_list) or not(company_name)) or (len(url_list) == 0):
            print("Problem in input provided")
            return
        
        tablename = f"producturls_{company_name}"
        if not(self.table_exists(tablename)):
            self.create_product_urls_table(tablename)
        

        try:
            cur = self.conn.cursor()

            # Prepare bulk insert query
            print("bulk insert")
            print(tablename)
            insert_query = f'''
            INSERT INTO {tablename} (url, company, timestamp)
            VALUES %s
            ON CONFLICT (url) DO UPDATE SET company = EXCLUDED.company;
            '''
            print("executing")
            # Prepare data for bulk insert
            
            # Execute bulk insert
            urls_so_far = set()
            new_url_list = []
            for url in url_list:
                if not(url[0] in urls_so_far):
                    urls_so_far.add(url[0])
                    new_url_list.append(url)
                else:
                    continue
            url_tuple = tuple(new_url_list)
            psycopg2.extras.execute_values(cur, insert_query, url_tuple)
            print("executed")
            
            # Commit the transaction
            self.conn.commit()

        except Exception as e:
            print(f"An error occurred: {e}")
            self.conn.rollback()
        finally:
            # Close cursor and connection
            cur.close()
    
    def disconnect(self):
        """Disconnect from the database. This function is destructive, will kill the object!"""
        self.conn.close()
        print("Disconnected from database")