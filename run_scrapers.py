import argparse
import multiprocessing
import importlib

# I need some logic of determining when the scrapers have last run - can add this to the database, maybe logs? Do so on each scraper run. 
# TODO: Add logic to run multiple python files as multiple processes.

def run_in_parallel(scrape_urls, scrape_products, residential_proxy, script_names):
    processes = []

    for script_name in script_names:
        # Dynamically import the module
        module = importlib.import_module(script_name)

        # Extract the main function
        main_func = getattr(module, 'main', None)
        if main_func is None:
            raise ImportError(f"No main function found in {script_name}")

        # Create a process for each main function
        process = multiprocessing.Process(target=main_func, args=(scrape_urls, scrape_products, residential_proxy))
        processes.append(process)

    # Start and then join all processes
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    print("Finished the processes!")

if __name__ == "__main__":
    print("Running all scrapers...")

    # List of script names (without .py extension)
    scraper_scripts = ['zara', 'hm']  # Add more script names here as needed

    parser = argparse.ArgumentParser(description='Run main functions from various scraping scripts with optional arguments')
    parser.add_argument('--scrape-urls', action='store_true', help='Scrape URLs if set')
    parser.add_argument('--scrape-products', action='store_true', help='Scrape products if set')
    parser.add_argument('--residential-proxy', action='store_true', help='Use residential proxies if set')
    args = parser.parse_args()

    run_in_parallel(args.scrape_urls, args.scrape_products, args.residential_proxy, scraper_scripts)