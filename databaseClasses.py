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
from person_classification import run_all_prediction


load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BATCH_SIZE = 5
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
        self.function_mapping = {
            "hm": self.parse_hm_urls,
            "zara": self.parse_zara_urls,
        }
        self.files = None

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
    
    def download_image(self, url, scraper):
        count = 0
        sess = scraper.setup_session()
        while count < 5:
            try:
                response = sess.get(url)
                if response.status_code == 200:
                    return BytesIO(response.content)
            except Exception as e:
                print(f"Error downloading image {url}: {e}")
            
            time.sleep(2)  # Wait before retrying
            sess = scraper.setup_session()  # Refresh the session
            count += 1
    
        print("Giving up on url", url)
        return None
        
    def get_hm_image(self, chosen_urls, scraper):
        download_url = chosen_urls[-3] if len(chosen_urls) >= 3 else (chosen_urls[-2] if len(chosen_urls) >= 2 else chosen_urls[-1])
        if download_url in self.files:
            return None, None
        download_url = self.make_valid_url(download_url)
        return download_url, None
    
    def get_zara_image(self, image_urls, scraper):
        for idx, url in enumerate(image_urls):
            # Now, we have to kind of figure out if there is a person in the image. To do so, we will quite literally do this multiprocessed - otherwise it becomes fairly bad.
            if url in self.files:
                continue
            
            image = self.download_image(url, scraper)
            is_person = run_all_prediction(image, "./yolov3.cfg", "./yolov3.weights")
            if not(is_person):
                main_url_index = idx
                break
            else:
                continue
        if main_url_index == -1:
            main_url_index = 0
        download_url = image_urls[main_url_index]
        if download_url in self.files:
            return None
        return download_url, image
    
    def get_right_image(self, image_urls, company, scraper):
        if company == "hm":
            chosen_urls = image_urls[0::3]
            download_url, image = self.get_hm_image(chosen_urls, scraper)
        
        elif company == "zara":
            # Try each url, if there is a person. If not, this becomes main image.
            download_url, image = self.get_zara_image(image_urls, scraper)
        
        if not(download_url):
            return None, None
        else:
            image = self.download_image(download_url, scraper) if not(image) else image
            return image, download_url
    
    def parse_hm_urls(self, rows, scraper):
        _, main_image_queue, other_image_queue = [], [], []
        urls = rows[:, 1]

        for url in urls:
            split_urls = url[1:-1].split("|" if "|" in url else ",")
            image, image_url = self.get_right_image(split_urls, "hm", scraper)
            if not(image):
                continue

            key = self.upload_to_s3(image, "hm", image_url)
            main_image_queue.append((image_url, key, "hm"))
            other_image_queue.extend([(u, "", "hm") for u in split_urls if u != image_url])

        return main_image_queue, other_image_queue
    
    def parse_zara_urls(self, rows, scraper):
        main_image_queue, other_image_queue = [], []
        urls = rows[:, 1]

        for url in urls:   
            split_urls = url.split("|") 
            image, image_url = self.get_right_image(split_urls, "zara", scraper)
            if not(image):
                continue
            key = self.upload_to_s3(image, "zara", image_url)
            main_image_queue.append((image_url, key, "zara"))
            other_image_queue.extend([(u, "", "zara") for u in split_urls if u != image_url])

        return main_image_queue, other_image_queue

    def upload_to_s3(self, image_bytes_io, company, original_url):
        mime_type, _ = mimetypes.guess_type(original_url)
        if mime_type is None:
            mime_type = 'image/jpeg'

        try:
            s3_key = self.get_s3_key_from_url(original_url)
            self.s3.put_object(
                Bucket=AWSS3Connection.bucket_name,
                Key=f"{company}/{s3_key}",
                Body=image_bytes_io.getvalue(),
                ContentType=mime_type
            )
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            return ""

    def parse_image_urls(self, rows, company, scraper):
        used_function = self.function_mapping[company]
        main_image_queue, other_image_queue = used_function(rows, scraper)
        return main_image_queue, other_image_queue 
    

    def filter_new_images(files, image_queue, get_s3_key):
        new_images = [url for url in image_queue if get_s3_key(url) not in files]
        return new_images
    
    

    def batched_image_upload(self, image_queue, scraper, company):
        num_batches = len(image_queue) // BATCH_SIZE + (len(image_queue) % BATCH_SIZE > 0)
        with ThreadPoolExecutor(max_workers=6) as executor:  # Adjust the number of workers as needed
            batches = [image_queue[i:i + BATCH_SIZE] for i in range(0, len(image_queue), BATCH_SIZE)]
            futures = [executor.submit(self.parse_image_urls, batch, company, scraper) for batch in batches]

            with tqdm(total=num_batches, desc="Batches completed", unit="batch") as pbar:
                for future in as_completed(futures):
                    batch_result = future.result()
                    # Now, update the pg database with the new url mappings.
                    scraper.pg.save_url_mapping(batch_result, company)
                    pbar.update(1)


    def upload_images_to_s3(self, scraper, upload_to_rds=False):
        query = f"""SELECT url, images, company
                    FROM productdata
                    ORDER BY unique_ids ASC;"""

        rows = scraper.pg.run_query(query)
        files = self.list_all_objects(self.s3, self.bucket_name)
        print(f"{len(files)} images already in S3.")
        rows = np.array(rows)
        self.files = files
        companies = np.unique(rows[:, 2])

        for company in companies:
            company_urls = rows[rows[:, 2] == company]
            self.batched_image_upload(company_urls, scraper, company)

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
            print(url_tuple)
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

    def save_url_mapping(self, rows):
        """Save the url mapping to the database."""
        if not(rows):
            print("No rows provided")
            return
        insert_query = f"INSERT INTO photo_mapping (url, aws_url, company) VALUES %s ON CONFLICT (url) DO NOTHING;"
        new_data = []

        for row in rows:
            if type(row) == list:
                new_data.append(tuple(row))
            else:
                continue

        #(image_url, key, "zara")
        with self.conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, insert_query, new_data)
        self.conn.commit()

    
    def disconnect(self):
        """Disconnect from the database. This function is destructive, will kill the object!"""
        self.conn.close()
        print("Disconnected from database")