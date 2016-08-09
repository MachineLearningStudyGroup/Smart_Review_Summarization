from pymongo import MongoClient
from srs import settings
import os

def connect_to_db():
	client = MongoClient('localhost', 27017)
	db = client['srs']
	return client, db

def disconnect_db(client):
	client.close()

def load_db_from_files():
	'''
	no useful value anymore
	'''
	client, db = connect_to_db()
	product_collection = db.product_collection

	# read files in scraper_data
	scraper_data = settings['scraper_data']
	for file0 in os.listdir(scraper_data):
		if file0.endswith('.txt'):
			product_id = file0[:-4]
			contents = []
			with open(os.path.join(scraper_data, file0), 'r') as file0_open:
				for line in file0_open:
					# get contents for each product
					contents.append(line)

			# create a document to insert
			product_document = {
			"product_id":product_id,
			"contents": contents,
			"ft_score": {},
			"ft_senIdx": {}
			}
			
			# insert
			product_collection.save(product_document)

	disconnect_db(client)

def select_for_product_id(product_id):
	client, db = connect_to_db()
	query_res = list(db.product_collection.find({"product_id": product_id}))
	disconnect_db(client)

	return query_res

def update_score_for_product_id(product_id, ft_score, ft_senIdx):

	client, db = connect_to_db()
	product_collection = db.product_collection

	query = {"product_id": product_id}
	update_field = {"ft_score": ft_score, "ft_senIdx":ft_senIdx}
	product_collection.update(query, {"$set": update_field}, True)

	client.close()

def update_num_reviews_for_product_id(product_id, num_reviews):

	client, db = connect_to_db()
	product_collection = db.product_collection

	query = {"product_id": product_id}
	update_field = {"num_reviews": num_reviews}
	product_collection.update(query, {"$set": update_field}, True)

	client.close()

def upsert_contents_for_product_id(product_id, product_name, contents, review_ids, ratings, review_ending_sentence, scraped_pages_new, num_reviews, category, ft_score = None, ft_senIdx = None):
	if ft_score is None:
		ft_score = {}
	if ft_senIdx is None:
		ft_senIdx = {}

	client, db = connect_to_db()
	product_collection = db.product_collection

	query = {"product_id": product_id}
	update_field = {
	"product_name": product_name,
	"contents": contents,
	"review_ids": review_ids,
	"ratings": ratings,
	"review_ending_sentence": review_ending_sentence,
	"scraped_pages": scraped_pages_new,
	"num_reviews": num_reviews,
	"category": category,
	"ft_score": ft_score, 
	"ft_senIdx": ft_senIdx
	}
	product_collection.update(query, {"$set": update_field}, True)

	client.close()

def update_contents_for_product_id(product_id, contents_new, review_ids_new, ratings_new, review_ending_sentence_new, scraped_pages_new, category_new, ft_score_new, ft_senIdx_new): 
	'''
	Query the content from db, and appends/update 
	'''
	query_res = select_for_product_id(product_id)
	contents = query_res[0]["contents"] + contents_new
	review_ids = query_res[0]["review_ids"] + review_ids_new
	ratings = query_res[0]["ratings"] + ratings_new
	scraped_pages = query_res[0]["scraped_pages"]

	category = query_res[0]["category"]
	if category_new and not category:
		category = category_new

	#Calculating the review_ending_sentence:
	review_ending_sentence = query_res[0]["review_ending_sentence"]
	if len(review_ending_sentence) > 0:
		last_sentence = review_ending_sentence[-1]
	else: 
		last_sentence = 0
	review_ending_sentence_new = [last_sentence + item for item in review_ending_sentence_new]
	review_ending_sentence = review_ending_sentence + review_ending_sentence_new

	scraped_pages = list(set(scraped_pages).union(scraped_pages_new))

	#merge two dictionary of lists
	ft_score = query_res[0]["ft_score"]
	ft_senIdx = query_res[0]["ft_senIdx"]
	key_as_ft = set(ft_score).union(ft_score_new)
	ft_score = dict((k, ft_score.get(k, []) + ft_score_new.get(k, [])) for k in key_as_ft)
	ft_senIdx = dict((k, ft_senIdx.get(k, []) + ft_senIdx_new.get(k, [])) for k in key_as_ft)

	client, db = connect_to_db()
	product_collection = db.product_collection
	query = {"product_id": product_id}
	update_field = {
		"contents": contents,
		"review_ids": review_ids,
		"ratings": ratings,
		"review_ending_sentence": review_ending_sentence,
		"scraped_pages": scraped_pages,
		"category": category,
		"ft_score": ft_score, 
		"ft_senIdx": ft_senIdx
	}
	product_collection.update(query, {"$set": update_field}, True)
	
	client.close()

if __name__ == '__main__':
	# function testing
	product_id = 'B00THKEKEQ'
	review_id = 'R3V15CFZSUNBQT'
	print has_review_id(product_id,review_id)
	res = select_for_product_id(product_id)
	res_content =  res[0]["ft_senIdx"]
	print res_content 