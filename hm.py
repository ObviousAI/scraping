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
ALL_URLS_SEEN = set()

def find_hrefs(soup, path):
    vals = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(path)]
    return set(vals)


def setup_session(scraper):
    header = scraper.get_browser_header()
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

    with tqdm(total=len(li_data), desc="Scraping HM Subcategory URLs") as pbar:
        for k, data in enumerate(li_data):
            _, href = data['text'], data['href']
            full_url = base_url + href + hm_query
            response = session.get(full_url)

            if response.status_code != 200:
                print("Could not get url!", full_url, flush=True)
                failed_urls.append(full_url)
                time.sleep(2 if response.status_code == 403 else 1)
            else:
                soup = BeautifulSoup(response.text, "html.parser")
                vals = find_hrefs(soup, href[:-5])
                all_urls.extend(list(vals))

            pbar.update(1)  # Update the progress bar after each iteration

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
    with tqdm(total=len(cleaned_urls), desc="Scraping URLs from categories") as pbar:
            for url in cleaned_urls:
                retry_count = 0
                max_retries = 3  # Set max retries to avoid infinite loop
                success = False

                while retry_count < max_retries and not success:
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
                        # Add timestamp to each URL. Make it so that vals is a list of lists.
                        # Add brand base url to each url.
                        vals = [[HM_BASE + url, str(time.time())] for url in vals]
                        final_urls.extend(list(vals))
                        success = True
                    else:
                        print("Failed to get URL:", full_url, "Status Code:", response.status_code)
                        time.sleep(2 if response.status_code == 403 else 1)
                        retry_count += 1

                pbar.update(1)  # Update the progress bar after each URL is processed

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
    if not os.path.exists('failed_urls_hm.txt'):
        open('failed_urls_hm.txt', 'w').close()
    
    with open('failed_urls_hm.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            failed_urls.append(line.strip())
    
    failed_urls = list(set(failed_urls))

    with open('failed_urls_hm.txt', 'w') as f:
        for url in failed_urls:
            f.write("%s\n" % url)


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
    pattern = re.compile(r'var productArticleDetails = ({.*?});', re.DOTALL | re.MULTILINE)
    script_content = script_tag.string if script_tag else ''
    match = pattern.search(script_content)
    if match:
        json_string = match.group(1)
        return json_string
    return None


def clean_and_load_json(json_string):
    try:
        #Remove all whitespace from the json string.
        json_string = json_string.replace("'", '"')
        json_string = re.sub(r"^$", "", json_string)
        json_string = re.sub(r"\s+", "", json_string)
        pattern = r'"images":\[.*?\],'

        #First get all image tag matches from above. These will be used to create the dictionary of items.
        image_array_matches = re.findall(pattern, json_string, flags=re.DOTALL)
        image_array_matches = [match for match in image_array_matches if match != '']

        # Now, clean the json string by removing the image array matches.
        cleaned_string = re.sub(pattern, '', json_string, flags=re.DOTALL)
        marketing_pattern = r'"marketingMarkers":\s*\[[^\]]*?\],'
        marketing_match = re.findall(marketing_pattern, cleaned_string, flags=re.DOTALL)

        # This part is to fetch the image urls which will be used down the line.

        matches = extract_image_urls(image_array_matches)

        # with open("image_urls.txt", "w") as f:
        #     json5.dump(matches, f, indent=4)
        
        if marketing_match:
            cleaned_string = re.sub(marketing_pattern, '', cleaned_string, flags=re.DOTALL)

        data = json5.loads(cleaned_string)
        

        # Reformat it using the standard json library to fix formatting
        fixed_json_string = json.dumps(data, indent=4)
        details = json5.loads(fixed_json_string)

        return details, matches
    except Exception as e:
        print("Error while cleaning the product details json.")
        return None, None

def extract_image_urls(all_patterns):
    image_pattern = r'"image":isDesktop\?"([^"]+)"'
    fullscreen_pattern= r'"fullscreen":isDesktop\?"([^"]+)"'
    thumbnail_pattern = r'"thumbnail":isDesktop\?"([^"]+)"'
    zoom_pattern = r'"zoom":isDesktop\?"([^"]+)"'
    img_array =[]
    try:
        for pattern in all_patterns:
            img_matches = re.findall(image_pattern, pattern, flags=re.DOTALL)
            fullscreen_matches = re.findall(fullscreen_pattern, pattern, flags=re.DOTALL)
            thumbnail_matches = re.findall(thumbnail_pattern, pattern, flags=re.DOTALL)
            zoom_matches = re.findall(zoom_pattern, pattern, flags=re.DOTALL)

            img_mapping = {}
            for i in range(len(img_matches)):
                img_mapping[i] = {}
                img_mapping[i]['image'] = img_matches[i] if i < len(img_matches) else ''
                img_mapping[i]['fullscreen'] = fullscreen_matches[i] if i < len(fullscreen_matches) else ''
                img_mapping[i]['thumbnail'] = thumbnail_matches[i] if i < len(thumbnail_matches) else ''
                img_mapping[i]['zoom'] = zoom_matches[i] if i < len(zoom_matches) else ''
            img_array.append(img_mapping)
        return img_array
            
    except Exception as e:
        print("Error in extracting image urls.")
        return None

def fix_gender_values(gender: str):
    # This function forces the gender values to be standardized according to our format.
    # The avaiilable values are "men, women, unisex"
    gender = gender.lower()
    if gender == 'ladies':
        return 'women'
    elif len(gender) == 0:
        return 'unisex'
    elif gender == 'all':
        return 'unisex'
    return gender
    

def process_product_details(product_article_details, images):
    product_data = []
    keys = [key for key in product_article_details.keys() if key.isdigit()]
    name = product_article_details.get('alternate', '')
    gender = name.split("-")[-1] if name else ''
    gender = gender.split("|")[0] if gender != '' else ''
    gender = fix_gender_values(gender)
    # Fix gender values to norms.

    code = product_article_details.get('articleCode', '')

    for idx, key in enumerate(keys):
        product = product_article_details[key]
        image_dict = images[idx]

        # From image_dict above, grab the relevant urls.
        if not(0 in image_dict):
            used_images = ""
        elif image_dict[0]["image"]:
            used_images = "|".join([image_dict[image]['image'] for image in image_dict])
        elif image_dict[0]["fullscreen"]:
            used_images = "|".join([image_dict[image]['fullscreen'] for image in image_dict])
        elif image_dict[0]["thumbnail"]:
            used_images = "|".join([image_dict[image]['thumbnail'] for image in image_dict])
        elif image_dict[0]["zoom"]:
            used_images = "|".join([image_dict[image]['zoom'] for image in image_dict])

        
        url_full = HM_BASE + product.get('url', '')
        prod_name = name.replace("{alternatecolor}", name)
        sizes = "|".join([size['name'] for size in product['sizes']])
        product_data.append([
            prod_name, gender, product.get('name', ''), product.get('description', ''),
            str(product.get('compositions', '')), product.get('whitePrice', '')[1:],
            sizes, used_images, url_full, 'hm', time.time()
        ])
        ALL_URLS_SEEN.add(url_full)
    return product_data


def extract_urls(json):
    # Define a regular expression pattern for URLs
    # This pattern looks for strings starting with "//" followed by any character except a space or a quote, 
    # until it hits a space, quote, or the end of the string
    url_pattern = r'"(//[^"\s]+)'

    # Use the findall method to find all occurrences of the pattern in the JavaScript code
    urls = re.findall(url_pattern, json)

    # Return the list of URLs
    return urls

def scrape_item(url, lst, response):
    soup = BeautifulSoup(response.text, "html.parser")

    script_content = extract_script_content(soup)
    if not script_content:
        print("No script tag found.")
        return False

    json_data, matches = clean_and_load_json(script_content)
    if not json_data:
        print("Failed to load JSON data.")
        return False

    try:
        product_data = process_product_details(json_data, matches)
        lst.extend(product_data)
        return True
    except Exception as e:
        print(e)
        print("Error in scraping item!", e, flush=True)
        return False
    

def scrape_items(scraper: Scraper, urls: list[str]):
    session = requests.Session()
    rows = []
    failed_urls = []
    pbar = tqdm(total=len(urls), desc="Scraping HM Products", leave=True)

    for i, url in enumerate(urls):
        if url in ALL_URLS_SEEN:
            continue
        time.sleep(0.2)
        if i % 5 == 0 and i != 0:
            time.sleep(2)
            scraper.save_product(rows)  # Replace with actual columns
            rows = []

        session = setup_session(scraper)

        try:
            response = session.get(url)
            if response.status_code == 200:
                if not(scrape_item(url, rows, response)):
                    failed_urls.append(url)
            else:
                handle_failed_url(scraper, session, response, failed_urls, url, rows)
        except Exception as e:
            failed_urls.append(url)

        pbar.update(1)

    pbar.close()
    scraper.save_product(rows)  # Replace with actual columns
    save_failed_urls(failed_urls)
    return


def main(scrape_urls_flag, scrape_products_flag, use_residential_proxy):
    if scrape_urls_flag:
        # Scrape both women and men urls.
        women_url = "https://www2.hm.com/en_us/women/products/view-all.html"
        scraper = Scraper(women_url, "hm", "https://www2.hm.com", use_residential_proxy)
        scraper.scrape_urls(lambda x, y: scrape_urls(scraper, x, y))

        time.sleep(10)

        men_url = "https://www2.hm.com/en_us/men/products/view-all.html"
        scraper = Scraper(men_url, "hm", "https://www2.hm.com", use_residential_proxy)
        scraper.scrape_urls(lambda x, y: scrape_urls(scraper, x, y))

        scraper.pg.remove_url_duplicates("hm")
        scraper.kill_db_connection()



    if scrape_products_flag:
        # Scrape product details.
        scraper = Scraper("", "hm", "https://www2.hm.com", use_residential_proxy)
        scraper.scrape_products(lambda x: scrape_items(scraper, x))
        scraper.pg.remove_product_duplicates("hm", "productdata")
        scraper.kill_db_connection()

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


    