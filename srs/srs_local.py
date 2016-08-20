from scraper import main as scraper_main, createAmazonScraper, scrape_num_review_and_category
from predictor import MaxEntropy_Predictor, Word2Vec_Predictor, loadTrainedPredictor
from srs import settings
from utilities import loadScraperDataFromDB, Sentence
from vanderModel import get_sentiment_score_for_sentences, get_ftScore_ftSenIdx_dicts
from sentiment_plot import box_plot
from database import (upsert_contents_for_product_id, 
update_score_for_product_id, update_num_reviews_for_product_id, 
update_contents_for_product_id, select_for_product_id, get_all_unique_registered_categories)
import os

def get_ft_dicts_from_contents(contents, predictor, start_idx = 0):
	sentences = []
	for cont in contents:
		sentences.append(Sentence(content=cont))
	
	predictor.predict_for_sentences(sentences)	#if Maxentropy, the cp_threshold=0.5, if Word2Vec, the cp_threshold should be 0.85 for criteria_for_choosing_class = "max", similarity_measure = "max"
	get_sentiment_score_for_sentences(sentences)
	return get_ftScore_ftSenIdx_dicts(sentences, start_idx)
	
def get_closest_registered_category(scraped_category, registered_categories):

	sim_scraped_category = [simplify_string(category_layer) for category_layer in scraped_category]

	registeredCategory_matchedLayer_dict = {}
	for registered_category in registered_categories:
		sim_registered_category = [simplify_string(category_layer) for category_layer in registered_category]
		matched_layers = []
		for layer in sim_scraped_category:
			if layer in sim_registered_category:
				matched_layers.append(1)
			else:
				matched_layers.append(0)
		registeredCategory_matchedLayer_dict[tuple(registered_category)] = matched_layers

	sorted_registeredCategory_matchedLayer_list = sorted(registeredCategory_matchedLayer_dict.items(),
		key=lambda item: item[1], reverse=True)

	return list(sorted_registeredCategory_matchedLayer_list[0][0])

def get_registered_category(product_id):
	"""
	Return a hirarchical category registered in the srs databse to which
	product belongs. The hirarchical category is mostly same as scraped category 
	from amazon, but the scraped category can change at amazon's will.
	This return registered category is associated with wordlist, which will be further 
	fed to predictor for sentence aspect classification. 
	"""
	_, scraped_category = scrape_num_review_and_category(product_id)

	registered_categories = get_all_unique_registered_categories()

	return get_closest_registered_category(scraped_category, registered_categories)


def simplify_string(string):

	return string.lower().replace(" ", "")

def fill_in_db(product_id, predictor_name = 'Word2Vec', review_ratio_threshold = 0.8, scrape_time_limit = 30):	
	# fetch product info from db
	query_res = select_for_product_id(product_id)

	if len(query_res) == 0: # not in db yet
		print "{0} not in db, now scraping...".format(product_id)
		# scrape product info and review contents:
		amazonScraper = createAmazonScraper()
		product_name, prod_contents, prod_review_ids, prod_ratings, review_ending_sentence, scraped_pages_new = scraper_main(amazonScraper, product_id, [], [], scrape_time_limit)
		prod_num_reviews, scraped_category = scrape_num_review_and_category(product_id)
		registered_categories = get_all_unique_registered_categories()
		registered_category = get_closest_registered_category(scraped_category, registered_categories)		
		if prod_num_reviews == -1:
			prod_num_reviews = len(prod_review_ids)

		# classify, sentiment score
		predictor = loadTrainedPredictor(predictor_name, registered_category)
		prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor)
		
		# insert new entry
		if len(prod_contents) > 0:
			upsert_contents_for_product_id(product_id, product_name, prod_contents, prod_review_ids,\
			 prod_ratings, review_ending_sentence, scraped_pages_new, prod_num_reviews, registered_category, \
				prod_ft_score_dict, prod_ft_senIdx_dict)
			return True
		else:
			print "Do not find reviews for %s" % product_id
			return False

	else:

		print "{0} already in db".format(product_id)
		# extract previous data in db:
		prod_contents = query_res[0]["contents"]
		prod_ft_score_dict = query_res[0]["ft_score"]
		prod_ft_senIdx_dict = query_res[0]["ft_senIdx"]
		prod_review_ids_db = query_res[0]["review_ids"]
		prod_scraped_pages = query_res[0]["scraped_pages"]
		if not prod_scraped_pages:
			prod_scraped_pages = []

		# scrape for total number of review and category
		prod_num_reviews, scraped_category = scrape_num_review_and_category(product_id)
		prod_num_reviews_previous = query_res[0]['num_reviews']

		registered_categories = get_all_unique_registered_categories()
		registered_category = get_closest_registered_category(scraped_category, registered_categories)

		num_review_db = len(query_res[0]["review_ids"])
		if prod_num_reviews == -1:
			prod_num_reviews = max(prod_num_reviews_previous, num_review_db)
		if prod_num_reviews > prod_num_reviews_previous:
			update_num_reviews_for_product_id(product_id, prod_num_reviews)
			print "updating product's num_reviews field"


		if num_review_db < review_ratio_threshold * prod_num_reviews and num_review_db < 100: 
			print "But not enough reviews in db, scrapping for more..."
			# scrape contents
			amazonScraper = createAmazonScraper()
			_, prod_contents_new, prod_review_ids, prod_ratings, review_ending_sentence, scraped_pages_new = \
			scraper_main(amazonScraper, product_id, prod_review_ids_db, prod_scraped_pages, scrape_time_limit)		

			# classify, get sentiment score
			predictor = loadTrainedPredictor(predictor_name, registered_category)
			if len(prod_contents_new) > 0:
				print "Filling scraped new reviews into db..."
				if len(prod_ft_score_dict) == 0 or len(prod_ft_senIdx_dict) == 0:				
					prod_contents = prod_contents + prod_contents_new
					prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor, start_idx = 0)
				else: # already has ft_scores calculated for previous contents:
					start_idx = len(prod_contents)
					prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents_new, predictor, start_idx = start_idx)
				
				# append new entry to existing entry
				update_contents_for_product_id(product_id, prod_contents_new, prod_review_ids, \
					prod_ratings, review_ending_sentence, scraped_pages_new, registered_category, \
					prod_ft_score_dict, prod_ft_senIdx_dict)
				return True

			else:
				print "Do not find new reviews for %s" % product_id
				if len(prod_ft_score_dict) == 0 or len(prod_ft_senIdx_dict) == 0:
					prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor)

					update_score_for_product_id(product_id, prod_ft_score_dict, prod_ft_senIdx_dict)

				return True

		else:
			print "enough reviews in db, getting scores..."
			if len(prod_ft_score_dict) == 0 or len(prod_ft_senIdx_dict) == 0:
				'''
				This only triggered if product review is loaded from file and not scraped directly
				'''
				# classify, sentiment score
				predictor = loadTrainedPredictor(predictor_name, registered_category)
				prod_ft_score_dict, prod_ft_senIdx_dict = \
				get_ft_dicts_from_contents(prod_contents, predictor)
				
				# update old entry
				update_score_for_product_id(product_id, prod_ft_score_dict, prod_ft_senIdx_dict)

				return True
			else:
				return True
	
	
def plot(product_id):
	_, prod1_ft_score_dict, _ = loadScraperDataFromDB(product_id)
	plot_folder = settings['sentiment_plot']
	figure_file_path = os.path.join(plot_folder, product_id + '_boxplot.png')
	box_plot(prod1_ft_score_dict, figure_file_path, product_id)

def main(product_id):
	fill_in_db(product_id)
	plot(product_id)

if __name__ == '__main__':
	product_id = 'B00HZE2PYI' # Samsung Galaxy Tab A 8-Inch Tablet
	main(product_id)