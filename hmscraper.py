import argparse
from concurrent.futures import ProcessPoolExecutor
import time
import re
import sys
import hashlib
import os
import random
import re
import requests
import json5
import json


import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm
from torpy.http.requests import TorRequests
from email.header import Header
from wsgiref import headers
from torpy.http.requests import TorRequests
from requests.exceptions import SSLError, HTTPError
from urllib.parse import urlparse, urlunparse


from databaseClasses import PostgressDBConnection
from Scraper import Scraper


load_dotenv()



HM_BASE = "https://www2.hm.com"

def find_hrefs(soup, path):
    vals = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(path)]
    return set(vals)


def setup_session(scraper):
    header = random.choice(scraper.headers)
    session = requests.Session()
    session.headers.update(header)
    session.proxies.update(scraper.get_proxy())
    return session


def extract_category_urls(session, url):
    response = session.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    span = soup.find_all('span', string="Shop by Product")
    ul = span[0 if "women" in url else 1].find_next_sibling('ul')
    li_elements = ul.find_all('li')
    return [{'text': li.get_text(strip=True), 'href': li.a['href']} for li in li_elements][1:]

def scrape_subcategory_urls(session, base_url, li_data, hm_query):
    all_urls = []
    failed_urls = []
    for k, data in enumerate(li_data):
        print(k, len(li_data))
        _, href = data['text'], data['href']
        full_url = base_url + href + hm_query
        response = session.get(full_url)
        if response.status_code != 200:
            print("Could not get url!", full_url, flush=True)
            failed_urls.append(full_url)
            time.sleep(2 if response.status_code == 403 else 1)
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        vals = find_hrefs(soup, href[:-5])
        all_urls.extend(list(vals))
    return all_urls

def clean_and_scrape_final_urls(session, scraper, base_url, all_urls, match_string):
    # Function to remove query parameters from URLs
    def clean_url(url):
        parsed_url = urlparse(url)
        return urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))

    # Remove duplicates, and clean the urls.
    cleaned_urls = [clean_url(url) for url in all_urls]
    final_urls = []

    # Now, loop through each url, and scrape the data. Do while loop, so that if there is an error, we can try again.
    for url in cleaned_urls:
        retry_count = 0
        max_retries = 3  # Set max retries to avoid infinite loop
        success = False

        while retry_count < max_retries and not success:
            print("Scraping URL:", url, "Attempt:", retry_count + 1)
            full_url = base_url + url

            # Get new header/proxy for each retry.
            header = scraper.get_browser_header()
            session.headers.update(header)
            session.proxies.update(scraper.get_proxy())

            time.sleep(0.5)  # Regular delay for each scrape attempt

            response = session.get(full_url)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                vals = find_hrefs(soup, match_string)
                final_urls.extend(list(vals))
                success = True
            else:
                print("Failed to get URL:", full_url, "Status Code:", response.status_code)
                time.sleep(2 if response.status_code == 403 else 1)
                retry_count += 1

    return final_urls

def scrape_urls(scraper: Scraper, url: str, base_url: str) -> list:
    hm_query = "?page-size=1500"
    match_string = "/en_us/productpage."

    session = setup_session(scraper)

    try:
        li_data = extract_category_urls(session, url)
        all_urls = scrape_subcategory_urls(session, base_url, li_data, hm_query)
        return clean_and_scrape_final_urls(session, scraper, base_url, all_urls, match_string)
    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except SSLError as ssl_err:
        print(f"SSL error occurred: {ssl_err}")
    except Exception as err:
        print(f"An error occurred: {err}")

    return []

def remove_trailing_commas(json_string):
    # This pattern finds a comma followed by any amount of whitespace and then a closing brace or bracket
    pattern = r',\s*([}\]])'
    # Replace any matches with just the closing brace or bracket
    return re.sub(pattern, r'\1', json_string)


def save_failed_urls(failed_urls):
    with open('failed_urls.txt', 'w') as f:
        for url in failed_urls:
            f.write("%s\n" % url)

def scrape_items(scraper: Scraper, urls: list[str]):
    session = requests.Session()
    rows = []
    failed_urls = []
    pbar = tqdm(total=len(urls), desc="Scraping HM Products", leave=True)

    for i, url in enumerate(urls):
        if i % 40 == 0 and i != 0:
            time.sleep(2)
            scraper.saveProduct(rows, scraper.columns)  # Replace with actual columns
            rows = []

        full_url = scraper.base_url + url
        header = scraper.get_browser_header()
        proxy = scraper.get_proxy()
        session.headers.update(header)
        session.proxies.update(proxy)

        try:
            response = session.get(full_url)
            if response.status_code == 200:
                if scrape_item(full_url, rows, response):
                    pbar.update(1)
                else:
                    failed_urls.append(full_url)
                    pbar.update(1)
            else:
                handle_failed_url(scraper, session, response, failed_urls, full_url, rows)
        except:
            failed_urls.append(full_url)

        # Reset the retry count if a successful request is made
        scraper.reset_retry_count()

    pbar.close()
    save_failed_urls(failed_urls)
    return rows

def handle_failed_url(scraper, session, response, failed_urls, url, rows):
    retry_count = 0 # Already tried once
    proxy = scraper.get_proxy()
    header = scraper.get_browser_header()
    session.headers.update(header)
    session.proxies.update(proxy)

    while retry_count < 3 and response.status_code != 200:
        print("Failed to get URL:", url, "Status Code:", response.status_code)
        time.sleep(2 if response.status_code == 403 else 1)
        response = session.get(url)
        retry_count += 1
    
    if response.status_code != 200:
        failed_urls.append(url)
    else:
        rows.append(scrape_item(url, rows, response))
    



def extract_script_content(soup):
    script_tag = soup.find('script', text=re.compile('productArticleDetails'))
    if not script_tag:
        return None
    return script_tag.string

def clean_and_load_json(script_content):
    json_string = script_content.replace("'", '"')
    cleaned_string = re.sub(r'^\s*$', '', json_string, flags=re.MULTILINE)
    return json5.loads(cleaned_string)

def extract_image_urls(all_patterns, idx):
    pattern = r'isDesktop \? "([^"]+)"'
    return re.findall(pattern, all_patterns[idx], flags=re.DOTALL)

def process_product_details(product_article_details, all_patterns):
    product_data = []
    keys = [key for key in product_article_details.keys() if key.isdigit()]
    name = product_article_details.get('alternate', '')
    gender = name.split(" ")[-4] if name else ''
    code = product_article_details.get('articleCode', '')


    for idx, key in enumerate(keys):
        product = product_article_details[key]
        images = extract_image_urls(all_patterns, idx)
        url_full = HM_BASE + product.get('url', '')
        prod_name = name.replace("{alternatecolor}", name)
        sizes = "|".join([size['name'] for size in product['sizes']])
        product_data.append([
            prod_name, gender, product.get('name', ''), product.get('description', ''),
            str(product.get('compositions', '')), product.get('whitePrice', ''),
            sizes, images, url_full, 'hm'
        ])
    return product_data


def extract_urls(json):
    # Define a regular expression pattern for URLs
    # This pattern looks for strings starting with "//" followed by any character except a space or a quote, 
    # until it hits a space, quote, or the end of the string
    url_pattern = r'"(//[^"\s]+)'

    # Use the findall method to find all occurrences of the pattern in the JavaScript code
    urls = re.findall(url_pattern, js_code)

    # Return the list of URLs
    return urls

def scrape_item(url, lst, response):
    soup = BeautifulSoup(response.text, "html.parser")

    script_content = extract_script_content(soup)
    if not script_content:
        print("No script tag found.")
        return False

    json_data = clean_and_load_json(script_content)
    if not json_data:
        print("Failed to load JSON data.")
        return False

    pattern = r'"images":\[.*?\],'
    all_patterns = re.findall(pattern, script_content, flags=re.DOTALL)
    try:
        product_data = process_product_details(json_data, all_patterns)
        lst.extend(product_data)
        return True
    except Exception as e:
        print("Error in scraping item!", e, flush=True)
        return False


def main(scrape_urls_flag, scrape_products_flag, use_residential_proxy):
    if scrape_urls_flag:
        # Scrape both women and men urls.
        women_url = "https://www2.hm.com/en_us/women/products/view-all.html"
        scraper = Scraper(women_url, "hm", "https://www2.hm.com")
        scraper.scrapeUrls(lambda x: scrape_urls(scraper, x))

        time.sleep(10)

        men_url = "https://www2.hm.com/en_us/men/products/view-all.html"
        scraper = Scraper(men_url, "hm", "https://www2.hm.com")
        scraper.scrapeUrls(lambda x: scrape_urls(scraper, x))

        scraper.pg.remove_url_duplicates("hm", "producturls")


    if scrape_products_flag:
        # Scrape product details.
        scraper = Scraper("", "hm", "https://www2.hm.com")
        scraper.scrapeProducts(lambda x: scrape_items(scraper, x))
        scraper.pg.remove_product_duplicates("hm", "productdata")

    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web scraping script for H&M products.')

    # Define the three arguments
    parser.add_argument('--scrape-urls', action='store_true', help='Scrape URLs if set')
    parser.add_argument('--scrape-products', action='store_true', help='Scrape products if set')
    parser.add_argument('--residential-proxy', action='store_true', help='Use residential proxies if set')

    # Parse the arguments
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    main(args.scrape_urls, args.scrape_products, args.residential_proxy)


    