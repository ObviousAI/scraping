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


from databaseClasses import PostgressDBConnection
from Scraper import Scraper


if __name__ == "__main__":
    # Create a scraper, and then create a listener.
    scraper = Scraper("", "hm", "https://www2.hm.com")
    scraper.create_listener()