import boto3
from dotenv import load_dotenv
from base64 import b64encode
import pandas as pd
import numpy as np
import requests
import urllib3

import uuid
from io import BytesIO
from collections import OrderedDict
import psycopg2
import psycopg2.extras
import hashlib
import os
import ast
import mimetypes
from tqdm import tqdm
from torpy.http.requests import TorRequests


AGENT_LIST = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:24.0) Gecko/20100101 Firefox/24.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:77.0) Gecko/20100101 Firefox/77.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/78.0.3904.70 Safari/537.36",
    "Mozilla/5.0 (X11; Linux i586; rv:31.0) Gecko/20100101 Firefox/31.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
]

load_dotenv()
s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ.get("AWSACCESSKEYID"),
    aws_secret_access_key=os.environ.get("AWSSECRETKEY"),
    region_name=os.environ.get("AWSREGION"),
    endpoint_url='https://s3.us-east-2.amazonaws.com',
)

def download_image(url):
    with TorRequests() as tor_requests:
        with tor_requests.get_session() as sess:
            # print the IP address of the proxy
            print(sess.get("http://httpbin.org/ip").json())
            html_content = sess.get(url, timeout=10).text
            # your scraping code here ..


def upload_to_s3(image_bytes_io, bucket_name, s3_filename, original_url):
    # Get the file extension from the original URL to determine the mime type
    mime_type, _ = mimetypes.guess_type(original_url)

    # Default to 'image/jpeg' if the mimetype can't be guessed
    if mime_type is None:
        mime_type = 'image/jpeg'

    try:
        s3.put_object(
            Bucket=bucket_name, 
            Key=s3_filename, 
            Body=image_bytes_io.getvalue(), 
            ContentType=mime_type  # Setting the ContentType is crucial
        )
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise e


def save_urls_db(url_list, company_name, gender):
    if (not(url_list) or not(company_name)) or (len(url_list) == 0):
        print("Problem in input provided")
        return
    #Save urls to postgress db
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("DATABASENAME"),
            user=os.environ.get("DATABASEUSER"),
            password=os.environ.get("DATABASEPASSWORD"),
            host=os.environ.get("DATABASEURL"),
            port=os.environ.get("DATABASEPORT")
        )
    except Exception as e:
        print(f"Could not connect to the database: {e}")
        exit(1)
    try:
        cur = conn.cursor()
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS productUrls (
            url TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            gender TEXT NOT NULL
        );'''
        
        cur.execute(create_table_query)
        conn.commit()

    except Exception as e:
        print(f"Could not create table: {e}")
        conn.rollback()
        conn.close()
        exit(1)

    try:
        delete_query = '''
        DELETE FROM productUrls
        WHERE company = %s AND url NOT IN %s;
        '''
        cur.execute(delete_query, (company_name, tuple(url_list)))
        conn.commit()
    except Exception as e:
        print(f"Could not delete rows: {e}")
        conn.rollback()

    try:
        url_tuple = tuple(url_list)
        # Delete rows for 'company_a' that are not in new_url_list
        delete_query = '''
        DELETE FROM productUrls
        WHERE company = %s AND url NOT IN %s;
        '''
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
        conn.commit()

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        # Close cursor and connection
        cur.close()
        conn.close()


def get_urls_from_db(company_name):
    if not company_name:
        print("Problem in input provided")
        return []
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("DATABASENAME"),
            user=os.environ.get("DATABASEUSER"),
            password=os.environ.get("DATABASEPASSWORD"),
            host=os.environ.get("DATABASEURL"),
            port=os.environ.get("DATABASEPORT")
        )
    except Exception as e:
        print(f"Could not connect to the database: {e}")
        exit(1)
        
    rows = []
    try:
        cur = conn.cursor()
        select_query = '''
        SELECT url, gender FROM productUrls
        WHERE company = %s;
        '''
        cur.execute(select_query, (company_name,))
        rows = cur.fetchall()
    except Exception as e:
        print(f"Could not select rows: {e}")
        conn.rollback()
    finally:
        # Close cursor and connection
        cur.close()
        conn.close()

    return [{"url": row[0], "gender": row[1]} for row in rows]


def save_product_details(df, company_name):
    """For this function, df should have the following fields:
        'Color', can be null.
        'Name', cannot be null
        'Description', can be null
        'Details', cannot be null.
        'Material', can be null.
        'Image_URLS', cannot be null (list)
        'Product_url', cannot be null
        'Size', cannot be null.
        'Availability' cannot be null
        'Gender', cannot be null,
    """
    if (not (isinstance(df, pd.DataFrame)) or not(company_name)):
        print("Problem in input provided")
        return
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("DATABASENAME"),
            user=os.environ.get("DATABASEUSER"),
            password=os.environ.get("DATABASEPASSWORD"),
            host=os.environ.get("DATABASEURL"),
            port=os.environ.get("DATABASEPORT")
        )
    except Exception as e:
        print(f"Could not connect to the database: {e}")
        exit(1)

    try:
        # need to generate an id for the items.
        cur = conn.cursor()
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS productDetails (
            id TEXT PRIMARY KEY,
            color TEXT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            details TEXT,
            material TEXT,
            image_urls TEXT NOT NULL,
            product_url TEXT NOT NULL,
            size TEXT NOT NULL,
            availability TEXT NOT NULL,
            company_name TEXT NOT NULL,
            gender TEXT NOT NULL
        );'''
        
        cur.execute(create_table_query)
        conn.commit()
    except Exception as e:
        print(f"Could not create table: {e}")
        conn.rollback()
        conn.close()
        exit(1)

    try:
        # Delete rows for 'company_a' that are not in the df provided. For this, calculate ids first.
        df['Image_URLS'] = df['Image_URLS'].apply(ast.literal_eval)
        df['image_urls'] = df['Image_URLS'].str.join("|")
        cols_to_check = ['Product_url', 'Details', 'Size', 'Description', 'Color']
        df_duplicated = df.duplicated(subset=cols_to_check, keep=False)
        df = df[df_duplicated]
        df['Id'] = df.apply(lambda x: make_uid(x), axis=1)
        ids = df['Id'].tolist()
        delete_query = '''
        DELETE FROM productDetails
        WHERE company_name = %s AND id NOT IN %s;
        '''
        cur.execute(delete_query, (company_name, tuple(ids)))
        conn.commit()
    except Exception as e:
        print(f"Could not delete rows: {e}")
        conn.rollback()

    print(df.iloc[0])
    data = [(row['Id'], row['Color'], row['Name'], row['Description'], row['Details'], row['Material'], row['image_urls'], row['Product_url'], row['Size'], row['Availability'], company_name, 'woman') for index, row in df.iterrows()]
    batch_size = 1000  # Choose an appropriate batch size
    num_batches = len(df) // batch_size + 1
    for i in range(num_batches):
        try:
            start_idx = i * batch_size
            end_idx = (i + 1) * batch_size
            batch_data = data[start_idx:end_idx]
            insert_query = '''
            INSERT INTO productDetails (id, color, name, description, details, material, image_urls, product_url, size, availability, company_name, gender)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET color = EXCLUDED.color, name = EXCLUDED.name, description = EXCLUDED.description, details = EXCLUDED.details, material = EXCLUDED.material, image_urls = EXCLUDED.image_urls, product_url = EXCLUDED.product_url, size = EXCLUDED.size, availability = EXCLUDED.availability, company_name = EXCLUDED.company_name, gender=EXCLUDED.gender;
            '''
            psycopg2.extras.execute_values(cur, insert_query, batch_data)
            conn.commit()
            print(f"Inserted batch {i + 1} of {num_batches}")

        except Exception as e:
            print(f"An error occurred while inserting batch {i + 1}: {e}")
            conn.rollback()

    cur.close()
    conn.close()
def get_image_url_mapping():
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("DATABASENAME"),
            user=os.environ.get("DATABASEUSER"),
            password=os.environ.get("DATABASEPASSWORD"),
            host=os.environ.get("DATABASEURL"),
            port=os.environ.get("DATABASEPORT")
        )
    except Exception as e:
        print(f"Could not connect to the database: {e}")
        exit(1)

    try:
        cur = conn.cursor()
        select_query = '''
        SELECT id, product_url, image_urls FROM productDetails;
        '''
        cur.execute(select_query)
        rows = cur.fetchall()
        rows = np.array(rows)
    except:
        print(f"Could not select rows: {e}")
        conn.rollback()
        exit()
    
    mapping = OrderedDict()
    if not(os.path.exists('i.npy')):
        np.save('i.npy', np.array([0]))
    i = np.load('i.npy')[0]
    print(i)
    print(i/len(rows) * 100, " percent done.")
    
    for row in tqdm(rows[i:]):
        #Each row, productDetails, splits the image_urls by | and then maps each image_url to the id. First link always has an https:// missing, and the next ones always have extra ones.
        image_urls = row[2].split('|')
        for url in image_urls:
            if url == '':
                continue
            if url[0:5] != 'https':
                url = 'https:' + url
            elif url[:14] == 'https:https://':
                url = url[6:]
            mapping[url] = hashlib.sha256(url.encode('utf-8')).hexdigest()
            if i == 0:
                print(url)
                print(mapping[url])
            image_bytes = download_image(url)
            upload_to_s3(image_bytes, 'scrapingphotos', mapping[url], url)
            np.save('i.npy', np.array([i]))
        i +=1
    
    #Convert mapping to a n x 2 array
    mapping = np.array(list(mapping.items()))

get_image_url_mapping()




    