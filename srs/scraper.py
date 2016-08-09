from configparser import ConfigParser, ExtendedInterpolation
import sys
from srs.amazon_scraper import AmazonScraper
import time
import datetime
import logging.config
import os.path
from utilities import getSentencesFromReview, Sentence, Review, Product, loadScraperDataFromDB
import nltk
from srs import settings
from database import select_for_product_id, upsert_contents_for_product_id
from lxml import html
import requests
from fake_useragent import UserAgent #install at: https://pypi.python.org/pypi/fake-useragent
import random


class AmazonReviewScraper:
    def __init__(self, access_key, 
        secret_key, assoc_tag, logger=None, debug=False):
        self.amzn = AmazonScraper(
            access_key,
            secret_key,
            assoc_tag)
        self.logger = logger or logging.getLogger(__name__)
        logging.config.fileConfig(
            os.path.join(
                settings["scraper_data"],
                "logging.ini"))
        self.debug = debug

    def _encode_safe(self, s):
        if s:
            return s.encode('utf-8')
        else:
            return ""

    def process_reviews(self, rs, item_id, id_db, id_list):
        """
        Inputs: Amazon Reviews object, and a filehandle.
        Output: Returns number of reviews processed. Writes reviews to file.
        """

        sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')

        count = 0
        output_str = ""
        contents = []
        review_ids = []
        ratings =[]
        review_sentence_num = []
        checker = len(id_db) > 0

        for r in rs.full_reviews():     
            try:
                if self.debug:
                    logging.debug(
                        "{} | {} | {}".format(
                            r.id, r.date, self._encode_safe(
                                r.text)))
                if r.text != "None":
                    if r.id in id_list:
                        print "Review already in current scraped list, pass"
                        continue
                    else:
                        if checker: # if we need to check reviewID
                            if r.id in id_db:
                                print 'scraped review is passed as it is in db'
                                continue 
                            else: 
                                count += 1
                                id_list.append(r.id)
                                sentenceContent_list = getSentencesFromReview(self._encode_safe(r.text))
                                print "First sentence: " + sentenceContent_list[0]
                                for content in sentenceContent_list:
                                    contents.append(content)
                                sentence_num = len(sentenceContent_list)
                                review_sentence_num.append(sentence_num)
                                review_ids.append(r.id)
                                ratings.append(float(r.rating) * 5) # rating directly from API is normalized to 1
                        else: #don't need to check reviewID
                            count += 1
                            id_list.append(r.id)
                            sentenceContent_list = getSentencesFromReview(self._encode_safe(r.text))
                            print "First sentence: " + sentenceContent_list[0]
                            for content in sentenceContent_list:
                                contents.append(content)
                            sentence_num = len(sentenceContent_list)
                            review_sentence_num.append(sentence_num)
                            review_ids.append(r.id)
                            ratings.append(float(r.rating) * 5) # rating directly from API is normalized to 1
            except:
                logging.warn('Encoding problem with review {}'.format(r.id))

        return count, contents, review_ids, ratings, review_sentence_num

    def scrape_reviews(self, item_id, prod_review_ids_db, prod_scraped_pages, scrape_time_limit = 30):
        """
        Fetches reviews for the Amazon product with the specified ItemId. 
        """

        start_time = time.time()
        current_time = start_time
        p = self.amzn.lookup(ItemId=item_id)
        rs = self.amzn.reviews(URL=p.reviews_url)

        count = 0
        page_count = 0
        contents = []
        review_ids =[]
        ratings = []
        review_sentence_num = []
        product_name = p.title
        id_list = []
        scraped_pages_new = []

        while current_time - start_time < scrape_time_limit:
            page_count += 1
            if page_count in prod_scraped_pages:
                print "Page {0} already scraped, go on to next page".format(page_count)
                if rs.next_page_url:
                    rs = self.amzn.reviews(URL = rs.next_page_url)
                    current_time = time.time()
                else:
                    print "Now is the last page."
                    break
            else:
                print "scraping page {0}:".format(page_count)
                result_tup = self.process_reviews(rs, item_id, prod_review_ids_db, id_list)
                count += result_tup[0]
                contents.extend(result_tup[1])
                review_ids.extend(result_tup[2])
                ratings.extend(result_tup[3])
                review_sentence_num.extend(result_tup[4])
                scraped_pages_new.append(page_count)
                current_time = time.time()
                print "time passed: %fs"%(current_time - start_time)

                if rs.next_page_url:
                    rs = self.amzn.reviews(URL = rs.next_page_url)
                
                else:
                    print "Now is the last page."
                    break
        
        # getting the cumulative list for review_ending_sentence
        if len(review_sentence_num) ==0:
            review_ending_sentence = []
        else:
            review_ending_sentence = [0]
            for num in review_sentence_num:
                review_ending_sentence.append(num + review_ending_sentence[-1]) 
            review_ending_sentence = review_ending_sentence[1:]

        end = time.time()
        logging.info(
            "Collected {} reviews for item {} in {} seconds".format(
                count, item_id, end - start_time))
        return product_name, contents, review_ids, ratings, review_ending_sentence, scraped_pages_new

def getAmazomConfidentialKeys():
    conf_file = os.path.join(
                settings["scraper_data"],
                "amazon.ini")
    conf = ConfigParser(interpolation=ExtendedInterpolation())
    try:
        conf.read(conf_file)
    except:
        sys.exit('Cannot read configuration file %s; exiting.' % conf_file)
    try:
        # str() is used to avoid HMAC-related unicode error
        AMAZON_ACCESS_KEY = str(conf.get('amazon', 'AMAZON_ACCESS_KEY'))
        AMAZON_SECRET_KEY = str(conf.get('amazon', 'AMAZON_SECRET_KEY'))
        AMAZON_ASSOC_TAG = str(conf.get('amazon', 'AMAZON_ASSOC_TAG'))
    except:
        sys.exit("Bad configuration file; exiting.")

    return AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_ASSOC_TAG

def createAmazonScraper():
    AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_ASSOC_TAG = \
    getAmazomConfidentialKeys()
    
    a = AmazonReviewScraper(
        AMAZON_ACCESS_KEY,
        AMAZON_SECRET_KEY,
        AMAZON_ASSOC_TAG,
        debug=False)
    return a

def getWebPage(productID): 
    url = "http://www.amazon.com/dp/" + productID
    print "Processing: " + url
    ua = UserAgent()
    headers = {
        # 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'}
        'User-Agent': ua.random}
        # get user agent: http://www.whoishostingthis.com/tools/user-agent/ 
        # or generate random one: https://pypi.python.org/pypi/fake-useragent
    page = requests.get(url, headers=headers)
    doc = html.fromstring(page.content)
    return doc

def scrape_reviews_hard(productID, prod_review_ids_db, max_scrape_loop = 1, current_loop=0):
    '''
    This method scraps directly from website and does not need userID or the AmazonScrape object
    However, it can only scrape the 5 top ranked review. 
    '''
    if current_loop > max_scrape_loop:
        return [], [], [], [], [], []
    else:
        try: 
            current_loop += 1
            doc = getWebPage(productID)
            XPATH_NAME = '//h1[@id="title"]//text()'
            XPATH_RATINGS = '//div[contains(@id, "rev-dpReviewsMostHelpfulAUI")]/div/div/a/i/span//text()'           
            XPATH_REVIEWS_IDS = '//div[contains(@id, "rev-dpReviewsMostHelpfulAUI")]/a[2]/@id'
            
            RAW_NAME = doc.xpath(XPATH_NAME)
            RAW_RATINGS = doc.xpath(XPATH_RATINGS)
            ratings = [int(float((x[:3]))) for x in RAW_RATINGS] #remove the rest of the string          
            RAW_REVIEWS_IDS = doc.xpath(XPATH_REVIEWS_IDS)
            
            product_name = ' '.join(''.join(RAW_NAME).split()) if RAW_NAME else None
            review_ids = [x[:x.index(".")] for x in  RAW_REVIEWS_IDS] #remove the rest of the string
            
            contents = []
            review_sentence_num = []
            ind_new_review = []
            for index in range(len(review_ids)):
                review_id = review_ids[index]
                if review_id in prod_review_ids_db:
                    print "scraped review is passed by backup_scraper as it is in db"
                    continue
                else:
                    ind_new_review.append(index)
                XPATH_REVIEW_BODY = '//div[contains(@id, "revData-dpReviewsMostHelpfulAUI-%s")]/div//text()' % review_id
                RAW_REVIEW_BODY = doc.xpath(XPATH_REVIEW_BODY)

                review_content = ""
                for RAW_REVIEW in RAW_REVIEW_BODY:
                    review = RAW_REVIEW.strip().encode('utf-8').decode('utf-8')
                    review_content += (review + " ")
                review_sentences = getSentencesFromReview(review_content)
                print "First sentence: {0}".format(review_sentences[0])
                sentence_num = len(review_sentences)
                review_sentence_num.append(sentence_num)
                contents.extend(review_sentences)

            if len(ind_new_review) > 0:
                print('new reviews available from scrape_reviews_hard')
                review_ids = [review_ids[j] for j in ind_new_review]
                ratings = [ratings[j] for j in ind_new_review]
            else:
                review_ids = []
                ratings = []

            #Getting review_ending_sentence:
            if len(review_sentence_num) == 0:
                review_ending_sentence = []
            else:
                review_ending_sentence = [0]
                for num in review_sentence_num:
                    review_ending_sentence.append(num + review_ending_sentence[-1]) 
                review_ending_sentence = review_ending_sentence[1:]

            scraped_pages_new = [1]

            return product_name, contents, review_ids, ratings, review_ending_sentence, scraped_pages_new
        except: 
            time.sleep(int(random.random() * 1.5 + 1) + random.random())
            print 'scraper failed, reinitiate for the %d th time' % current_loop
            return scrape_reviews_hard(productID, checker, max_scrape_loop, current_loop)


def scrape_num_review_and_category(productID, max_scrape_loop = 2, current_loop=0):
    '''
    return total number of reviews from the page
    '''
    if current_loop > max_scrape_loop:
        return -1, []
    else:
        try:
            current_loop += 1
            doc = getWebPage(productID)

            XPATH_TOTAL_REVIEW = '//div[contains(@id, "averageCustomerReviews")]/span[3]/a/span/text()'
            RAW_TOTAL_REVIEW = doc.xpath(XPATH_TOTAL_REVIEW)
            ind = RAW_TOTAL_REVIEW[0].index('c')
            num_review_raw = RAW_TOTAL_REVIEW[0][:ind-1] # example: 1,029 customer reviews 
            num_review = int(num_review_raw.replace(',', ''))

            XPATH_CATEGORY = '//a[@class="a-link-normal a-color-tertiary"]//text()'
            RAW_CATEGORY = doc.xpath(XPATH_CATEGORY)
            category = [i.strip() for i in RAW_CATEGORY] if RAW_CATEGORY else None
            
            return num_review, category
        except: 
            # reinitiate if failed
            print 'scraper for num_and_category failed, reinitiate for the %d th time'%current_loop
            time.sleep(int(random.random() * 1.5 + 1) + random.random())
            return scrape_num_review_and_category(productID, max_scrape_loop, current_loop)


def main(amazonScraper, product_id, prod_review_ids_db, prod_scraped_pages, scrape_time_limit = 30):
    try: 
        product_name, contents, review_ids, ratings, review_ending_sentence, scraped_pages_new = \
            amazonScraper.scrape_reviews(product_id, prod_review_ids_db, prod_scraped_pages, scrape_time_limit)
        if len(contents) > 0:
            return product_name, contents, review_ids, ratings, review_ending_sentence, scraped_pages_new
        else:
            print "Amazon API scraper does not return contents, try backup scraper..."
            return scrape_reviews_hard(product_id, prod_review_ids_db)
    except:
        # backup scraper 
        print 'Amazon API failed. Scrape the hard way!'
        return scrape_reviews_hard(product_id, prod_review_ids_db)


if __name__ == "__main__":
    # function testing 
    productID = 'B00I8BICB2' # B00I8BICB2 sony a6000 with 686 reviews,B00T85PH2Y,B00HZE2PYI,B00C7NX884
    productID = 'B0046UR4F4'
    productID = 'B00000JDEE'

    a = createAmazonScraper()
    result = main(a,productID, [], [], 500)
    print result