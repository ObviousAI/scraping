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
    AGENT_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0"
    ]
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


    def upload_images_to_s3(self, brand, scraper, upload_to_rds = False):
        """ Upload images to s3 bucket.
            To do this, initially create an instance of the PostgressDBConnection class, and run a select query to get all the necessary information from the database.
            Then, hash the information and push to database.
            If upload to rds is true, also upload the mappings to rds."""
        #TODO: Create the same query as below, but sort by ascending unique_ids column
        # This way, we can get the images in the order they were scraped.
        # This is important for the image classifier.
        query = f"""SELECT url, images
                        FROM productdata
                            WHERE brand = '{brand}'
                                ORDER BY unique_ids ASC;
                                                    """
        #Parse image urls from databse
        # They are seperated by a delimeter, so split them.
        # Only grab the ones that end with [file:/product/fullscreen]
        rows = scraper.pg.run_query(query)
        # Get all filenames from s3. Then, compare.
        files = self.list_all_objects(self.s3, self.bucket_name)
        print(len(files), " images already in S3.") 
        rows = np.array(rows)
        # Get urls, so first element in each row.
        image_urls = []
        urls = rows[:, 1]
        main_image_queue, other_image_queue = [], []
        # Now split each ones, and add all of them to list.
        for url in urls:
            if "|" in url:
                split_urls = url[1:-1].split("|")
            else:
                split_urls = url[1:-1].split(",")
            # Grab only the ones in indices 1, 4, 7, 10, 13, 16, 19, 22, 25, 28...
            split_urls = split_urls[0::3]
            if len(split_urls) >= 3:
                best_image_url = split_urls[-3]
            elif len(split_urls) >= 2:
                best_image_url = split_urls[-2]
            else:
                best_image_url = split_urls[-1]
            s3key = self.get_s3_key_from_url(best_image_url)
            other_images = [url for url in split_urls if not(url == best_image_url)]
            if not(s3key in files):
                main_image_queue.append(best_image_url)
            for split_url in other_images:
                s3_key = self.get_s3_key_from_url(split_url)
                if not(s3_key in files):
                    other_image_queue.append(split_url) 

        
        image_urls.extend(main_image_queue)
        image_urls.extend(other_image_queue)   
        print(len(image_urls), " images to be added to s3")
        # Upload images to s3 using rows. Use proxies provided by aws.
        self.process_url_images(image_urls, scraper)



    # def process_url_images(self, urls_chunk, scraper):
    #     """ Method to actually save the images in our own boto3 (AWS S3) bucket.
    #         For now, I am not using any multiprocessing, but this can be done in the future.
    #     """
    #     s3 = AWSS3Connection.initialize_s3(None)
    #     failed_images = []
    #     for sub_start in tqdm(range(0, len(urls_chunk), 10)):
    #         urls= urls_chunk[sub_start:sub_start+10]
            
    #         # Create a new session -> get a random proxy from firefox_proxy method, and then update the session with the proxy.
    #         # Also grab a random user agent from the list of user agents.
    #         # TODO: Update the user agents, I think we are running out of good ons.
    #         # We are doing 10 loops at once instead - get 10 images, then upload them as a batch.

    #         proxy = scraper.datacenter_proxy()
    #         agent = random.choice(scraper.headers)
    #         header = {
    #             'User-Agent': agent,
    #             'origin': 'https://www2.hm.com'
    #         }
    #         session = requests.Session()
    #         session.proxies.update(proxy)
    #         session.headers.update(header)
            
    #         new_urls = []
    #         for url in urls:
    #             if url.startswith("//"):
    #                 full_url = "https:" + url
    #             elif url.startswith("/"):
    #                 full_url = "https:/" + url
    #             new_urls.append(full_url)
    #         try: 
    #             images = []
    #             for url in new_urls:
    #                 image_bytes = AWSS3Connection.download_image(None, full_url, session, scraper)

    #             if image_bytes == None:
    #                 continue
    #             AWSS3Connection.upload_to_s3(None, s3, image_bytes, url, full_url) 
    #         except Exception as e:
    #             print("Error downloading image")
    #             failed_images.append(url)
    #             print(e)
    #             continue
    #     # Save failed images locally, so we can try again later.
    #     with open("failed_images.txt", "a") as f:
    #         for image in failed_images:
    #             f.write(image + "\n")


@dataclass
class Column(): 
    name: str
    type: str
    isNull: bool
    isPrimary: bool
    

class PostgressDBConnection():
    def __init__(self, table_name = "productdata", isAWS = True):
        """Initialize the connection to the PostgressSQL database. Make an bject for this for every table you want to connect to, so the logic stays intact. Database can take up to 20 connections at once at the moment."""
        if isAWS:
            self.conn = psycopg2.connect(
                dbname=os.environ.get("AWSDBNAME"),
                user=os.environ.get("AWSDBUSER"),
                password=os.environ.get("AWSDBPASSWORD"),
                host=os.environ.get("AWSDBURL"),
                port=os.environ.get("AWSDBPORT"),
                sslmode='require'
            )
        else:
            self.conn = psycopg2.connect(
                dbname=os.environ.get("DATABASENAME"),
                user=os.environ.get("DATABASEUSER"),
                password=os.environ.get("DATABASEPASSWORD"),
                host=os.environ.get("DATABASEURL"),
                port=os.environ.get("DATABASEPORT")
            )
        self.table_name = table_name

    def create_product_table(self):
        """Columns are the following:
            columns = ['unique_ids', 'name', 'gender', 'color', 'description', 'compositions', 'price', 'sizes', 'images', 'url', 'brand']
        """
        # Create table using self.pg.conn. Just hardcode the above column value, unique_ids being the key of table.
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS productdata (
            unique_ids serial PRIMARY KEY,
            name TEXT,
            gender TEXT,
            color TEXT,
            description TEXT,
            compositions TEXT,
            price TEXT,
            sizes TEXT,
            images TEXT,
            url TEXT,
            brand TEXT
        );"""

        try:
            # Create a cursor object and execute the SQL statement
            cursor = self.conn.cursor()
            cursor.execute(create_table_sql)
            # Commit the changes to the database
            self.conn.commit()
            print("Table 'productdata' created or already exists.")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error: {error}")
        finally:
            # Close the cursor and the database connection
            cursor.close()
        
        
    def create_product_urls_table(self):
        """ Create new table, with fields url and brand"""
        sql_query = """
        CREATE TABLE IF NOT EXISTS producturls (
            unique_ids serial PRIMARY KEY,
            url TEXT,
            brand TEXT
        );"""

        try:
            # Create a cursor object and execute the SQL statement
            cursor = self.conn.cursor()
            cursor.execute(sql_query)
            # Commit the changes to the database
            self.conn.commit()
            print("Table 'product_urls' created or already exists.")
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
        
    def remove_duplicates_in_database(self, brand, tablename):
        """Remove duplicates in the database, based on the url. Remove only for given brand (to keep it safe/shorter runtime)"""
        query = f"""DELETE FROM {tablename} 
                    WHERE unique_ids NOT IN (
                        SELECT MIN(unique_ids) 
                        FROM {tablename} 
                        WHERE brand = '{brand}' 
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

    def run_query(self, query):
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
            self.create_product_urls_table()

        if not(data):
            print("No data provided")
            return
        
        if not(columns):
            print("No columns provided")
            return
        
        
        insert_query = f"INSERT INTO {tablename} ({','.join([column for column in columns])}) VALUES %s ON CONFLICT (unique_ids) DO NOTHING;"
        with self.conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, insert_query, [tuple(row) for row in data])
        self.conn.commit()



    def save_urls_db(self, tablename, url_list, company_name, gender):
        if (not(url_list) or not(company_name)) or (len(url_list) == 0):
            print("Problem in input provided")
            return
        
        if not(self.table_exists(tablename)):
            columns = [Column("url", "TEXT", True, True), Column("company", "TEXT", True, False), Column("gender", "TEXT", True, False)]
            self.create_table(tablename, columns)
            self.table_name = tablename

        
        query = f"SELECT url FROM {self.table_name} WHERE company = '{company_name}';"
        self.run_query(query)  

        try:
            url_tuple = tuple(url_list)
            # Delete rows for 'company_a' that are not in new_url_list
            delete_query = '''
            DELETE FROM productUrls
            WHERE company = %s AND url NOT IN %s;
            '''
            cur = self.conn.cursor()
            cur.execute(delete_query, (company_name, url_tuple))
            
            # Prepare bulk insert query
            insert_query = '''
            INSERT INTO productUrls (url, company, gender)
            VALUES %s
            ON CONFLICT (url) DO UPDATE SET company = EXCLUDED.company;
            '''
            
            # Prepare data for bulk insert
            data = [(url, company_name, gender) for url in url_tuple]
            
            # Execute bulk insert
            psycopg2.extras.execute_values(cur, insert_query, data)
            
            # Commit the transaction
            self.conn.commit()

        except Exception as e:
            print(f"An error occurred: {e}")
            self.conn.rollback()
        finally:
            # Close cursor and connection
            cur.close()
            self.conn.close()

    def select_query(self, query):
        """Run a select query on the database."""
        try:
            curr = self.conn.cursor()
            curr.execute(query)
            self.conn.commit()
            return curr.fetchall()
        except:
            self.conn.rollback()
            raise Exception("Error running select query")
    
    def disconnect(self):
        """Disconnect from the database. This function is destructive, will kill the object!"""
        self.conn.close()
        print("Disconnected from database")
        del self