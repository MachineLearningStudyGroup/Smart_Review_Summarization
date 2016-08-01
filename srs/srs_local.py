from scraper import main as scraper_main, createAmazonScraper, scrape_num_review_and_category
from predictor import MaxEntropy_Predictor, Word2Vec_Predictor, loadTrainedPredictor
from srs import settings
from utilities import loadScraperDataFromDB, Sentence
from swnModel import get_sentiment_score_for_sentences, get_ftScore_ftSenIdx_dicts
from sentiment_plot import box_plot
from database import upsert_contents_for_product_id, update_for_product_id, update_contents_for_product_id, select_for_product_id
import os

def get_ft_dicts_from_contents(contents, predictor, start_idx = 0):
	sentences = []
	for cont in contents:
		sentences.append(Sentence(content=cont))
	
	predictor.predict_for_sentences(sentences)	#if Maxentropy, the cp_threshold=0.5, if Word2Vec, the cp_threshold should be 0.85 for criteria_for_choosing_class = "max", similarity_measure = "max"
	get_sentiment_score_for_sentences(sentences)
	return get_ftScore_ftSenIdx_dicts(sentences, start_idx)
	

def fill_in_db(product_id, predictor_name = 'MaxEntropy', review_ratio_threshold = 0.8, scrape_time_limit = 30):	
	# fetch product info from db
	prod_contents, prod_ft_score_dict, prod_ft_senIdx_dict = loadScraperDataFromDB(product_id)

	if len(prod_contents) == 0: # not in db yet
		print "{0} not in db, now scraping...".format(product_id)
		# scrape product info and review contents:
		amazonScraper = createAmazonScraper()
		product_name, prod_contents, prod_review_ids, prod_ratings, review_ending_sentence = scraper_main(amazonScraper, product_id, True, scrape_time_limit)
		prod_num_reviews, prod_category = scrape_num_review_and_category(product_id)

		# classify, sentiment score
		predictor = loadTrainedPredictor(predictor_name)
		prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor)
		
		# insert new entry
		if len(prod_contents) > 0:
			upsert_contents_for_product_id(product_id, product_name, prod_contents, \
				prod_review_ids, prod_ratings, review_ending_sentence, prod_num_reviews, prod_category,\
				prod_ft_score_dict, prod_ft_senIdx_dict)
			return True
		else:
			print "Do not find reviews for %s" % product_id
			return False

	else:

		print "{0} already in db".format(product_id)
		# scrape for total number of review and category
		prod_num_reviews, prod_category = scrape_num_review_and_category(product_id)
		query_res = select_for_product_id(product_id)
		if not prod_num_reviews:
			prod_num_reviews = query_res[0]['num_reviews']
		num_review_db = len(query_res[0]["review_ids"])


		if num_review_db < review_ratio_threshold * prod_num_reviews and num_review_db < 100: 
			print "But not enough reviews in db, scrapping for more..."
			# scrape contents
			amazonScraper = createAmazonScraper()
			_, prod_contents_new, prod_review_ids, prod_ratings, review_ending_sentence = scraper_main(amazonScraper, product_id, True, scrape_time_limit)		

			# classify, get sentiment score
			predictor = loadTrainedPredictor(predictor_name)
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
					prod_ratings, review_ending_sentence, prod_num_reviews, prod_category, \
					prod_ft_score_dict, prod_ft_senIdx_dict)
				return True

			else:
				print "Do not find new reviews for %s" % product_id
				if len(prod_ft_score_dict) == 0 or len(prod_ft_senIdx_dict) == 0:
					prod_contents = prod_contents + prod_contents_new
					prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor)

					update_for_product_id(product_id, prod_ft_score_dict, prod_ft_senIdx_dict)

				return True

		else:
			print "enough reviews in db, getting scores..."
			if len(prod_ft_score_dict) == 0 or len(prod_ft_senIdx_dict) == 0:
				'''
				This only triggered if product review is loaded from file and not scraped directly
				'''
				# classify, sentiment score
				predictor = loadTrainedPredictor(predictor_name)
				prod_ft_score_dict, prod_ft_senIdx_dict = \
				get_ft_dicts_from_contents(prod_contents, predictor)
				
				# update old entry
				update_for_product_id(product_id, prod_ft_score_dict, prod_ft_senIdx_dict)

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
	product_id = 'B00HV6KL6Y'
	main(product_id)