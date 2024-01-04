from concurrent.futures import ProcessPoolExecutor
import time
import re
import sys
import argparse
import os
import random
import signal
import re


from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm
from urllib.parse import quote_plus

from databaseClasses import PostgressDBConnection, AWSS3Connection
from email.header import Header
from wsgiref import headers
from torpy.http.requests import TorRequests
import urllib.request
import random

load_dotenv()

class Scraper():

    proxies_all = "https://customer-ardaakman:Scriep123@pr.oxylabs.io:7777"
    # Split the proxies into a list, and split each proxy into the relevant fields (username, password, endpoint, port)

    def __init__(self, startingUrl, company, brand_base_url, residentialProxy = False, ignoreUpdates= True, product_database = "productdata", autocommit = False):
        # Name of company that is being scraped.
        self.company = company
        # Starting url of the scraped company.
        self.startingUrl = startingUrl

        ## Connect to pg database on aws
        self.pg = PostgressDBConnection(table_name="productdata", autocommit = True)
        self.aws = AWSS3Connection()
        self.ignoreUpdates = ignoreUpdates

        # Leave empty string, if urls scraped are absolute/have base url.
        self.brand_base_url = brand_base_url
        self.product_database = product_database

        #Read from proxies.txt and headers.txt
        with open("./cached_data/proxies.txt", "r") as file:
            self.datacenter_proxies = file.readlines()
        self.datacenter_proxies = [x.strip() for x in self.datacenter_proxies]
        
        with open("./cached_data/headers.txt", "r") as file:
            self.agents = file.readlines()
        self.agents = [x.strip() for x in self.agents]

        self.use_residential_proxy = residentialProxy

        self.residential_proxy = "9ROhXWh4YAaauHEV:wifi;;;;@rotating.proxyempire.io:9000"

        #Default column values used in the database. Do not change if the database columns are the same.
        self.columns  = ['name', 'gender', 'color', 'description', 'compositions', 'price', 'sizes', 'images', 'url', 'company']

        #Column names for the urls table in database.
        self.url_columns = ["url", "company", "gender", "timestamp"]

    
    def get_proxy(self):
        if self.use_residential_proxy:
            return self.get_residential_proxy()
        else:
            return self.get_datacenter_proxy()
        
    def get_datacenter_proxy(self) -> dict:
        proxy = random.choice(self.datacenter_proxies)
        provider = {
            "http": f"http://{proxy}",
        }
        # Create the proxy dictionary, return it
        return provider


    def get_residential_proxy(self) -> dict:
        # Construct the proxy string with authentication.

        # Construct the proxies dictionary
        proxies = {
            "https": f"https://{self.residential_proxy}",
            "http": f"http://{self.residential_proxy}"
            }

        return proxies


    def get_browser_header(self) -> str:
        # Return a browser agent, that will be used in the header for the HTTP(S) request.
        agent = random.choice(self.agents)
        header = {
            "User-Agent": agent,
            "origin": self.brand_base_url
        }
        return header


    def create_driver(self):
        # Used to create a driver with the necessary headers and ipv6 address. (source ip)
        
        header = random.choice(self.AGENT_LIST)
        proxy_settings = self.firefox_proxy(header)

        seleniumwire_options = {
            'proxy': {
                'http': proxy_settings["http"],
                'no_proxy': 'localhost,127.0.0.1',
            }
        }

        # If your proxy requires authentication, add the credentials
        if 'username' in proxy_settings and 'password' in proxy_settings:
            seleniumwire_options['proxy']['username'] = proxy_settings['username']
            seleniumwire_options['proxy']['password'] = proxy_settings['password']

        # Configure additional options for Chrome
        chrome_options = webdriver.ChromeOptions()

        # Initialize the WebDriver with the specified options
        driver = webdriver.Chrome(
            seleniumwire_options=seleniumwire_options,
            chrome_options=chrome_options
        )
        return driver

    def scrape_products(self, fn):
        """Function that scrapes the actual urls from a website and returns this."""
        if not(self.ignoreUpdates):
            old_products = self.pg.run_query(f"SELECT url FROM productdata_{self.company} WHERE company = '{self.company}'")
            #set of old product urls
            old_set = set(old_products[:,0])
        else:
            old_set = set()

        urls = self.pg.run_query(f"SELECT url FROM producturls_{self.company} WHERE company = '{self.company}'")
        urls = urls[:,0]
        urls = [url for url in urls if url not in old_set]
        

        prods = fn(urls)
        self.save_product(prods)
    

    def scrape_urls(self, fn):
        connection_established = self.pg.test_connection()
        if not connection_established:
            print("Could not establish connection to database. Exiting...")
            sys.exit(1)

        table_exists = self.pg.table_exists(f"producturls_{self.company}")
        if not(self.ignoreUpdates) and table_exists:
            old_products = self.pg.run_query(f"SELECT url FROM producturls WHERE company = '{self.company}'")
            old_set = set(old_products[:, 0])
        else:
            old_set = set()

        vals = fn(self.startingUrl, self.brand_base_url)
        result_urls = []
        for val in vals:
            if val[0] not in old_set:
                result_urls.append((val[0], self.company, val[1]))

        # Result urls contains the [url, company, geder, timestamp]!
        self.save_urls(result_urls)
        return result_urls
    

    def fetchProductsFromDb(self):
        query = f"SELECT * FROM products WHERE company = '{self.company}'"
        return self.pg.run_query(query)
    
    
    def process_urls_in_chunk(self, urls_chunk, mapping, i, lock):
            sub_chunk_size = 5  # Number of URLs to process before switching session
            # Break the urls_chunk into smaller sub-chunks
            for sub_start in range(0, len(urls_chunk), sub_chunk_size):
                sub_chunk = urls_chunk[sub_start:sub_start + sub_chunk_size]
                subchunk_processed_count = 0
                vals = []
                with TorRequests() as tor_requests:
                    with tor_requests.get_session() as sess:
                        HEADERS = {"User-Agent": random.choice(self.AGENT_LIST)}
                        print(sess.get("http://httpbin.org/ip").json())
                        print(HEADERS["User-Agent"])
                        for url in tqdm(sub_chunk):
                            bs = BeautifulSoup(sess.get(url).text, 'html.parser')
                            val = self.scrapeSingleProduct(bs, url)
                            vals.append(val)
                #Store vals in database.
                self.pg.save_product_details(vals)
                print(f"Subchunk {i} processed {subchunk_processed_count} urls")

    def save_urls(self, urls):
        """Function that saves the urls to the database."""
        self.pg.save_urls_db(urls, self.company)

    def save_product(self, product):
        """"Here are the columns:
                'Unique ID': sha256_hash,
                'Color': product_color,
                'Name': product_name,
                'Description': product_long_desc,
                'Details': product_details,
                'Material': material_type,
                'Image_urls': secondary_image_urls,
                'Product_url': color_url,
                'Size': size,
                'Size Availability': availability,
                'Gender': gender,
                'Price': product_price,
            """
        self.pg.save_data_to_db(f"productdata_{self.company}", product, self.columns)


    def scrape_single_product(self, driver,  url , fn):
        """"This function should get the details of the product. The requred fields are:
        - product_name
        - product_color
        - product_description
        - avaliable_sizes
        - Material information
        - image_urls
        Function can change per website.
        """
        return fn(driver, url)
    
    def create_listener(self):
        self.pg.conn.autocommit = True
        curs = self.pg.conn.cursor()
        curs.execute("LISTEN productdata_channel;")
        print("Listening for notifications on channel 'productdata_channel'")

        try:
            while True:
                # Check for connection status here
                print("Waiting for notifications...")

                self.pg.conn.poll()
                while self.pg.conn.notifies:
                    notify = self.pg.conn.notifies.pop(0)
                    print(f"Received notification: {notify.payload}")
                    # Run the image update function here
                    self.aws.upload_images_to_s3(self.company, self)

                # Sleep for a short period to prevent high CPU usage, adjust the time as needed
                time.sleep(5)
        except Exception as e:
            print(f"An error occurred: {e}")
    
    def kill_db_connection(self):
        self.pg.disconnect()
        




    






