from databaseClasses import PostgressDBConnection
from Scraper import Scraper


if __name__ == "__main__":
    # Create a scraper, and then create a listener.
    scraper = Scraper("", "hm", "https://www2.hm.com", autocommit = True)
    scraper.create_listener()