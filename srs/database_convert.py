from pymongo import MongoClient, ASCENDING
from utilities import getSentencesFromReview
from srs_local import get_ft_dicts_from_contents
from predictor import loadTrainedPredictor
import gzip
import ast

def connect_to_db():
	client = MongoClient('localhost', 27017)
	db = client['srs']
	return client, db

def upsert_review_for_product_id(review, db_product_collection, meta_dict):
	"""For each review, if it belongs to the category indicated by "category_name", add it to the product_collection in db"""
	product_id = review['asin']
	query_res = list(db_product_collection.find({"product_id": product_id}))

	contents_new = getSentencesFromReview(review['reviewText'])
	num_sentence = len(contents_new)
	review_id_new = review['reviewerID']
	rating_new = review['overall']

	isfound = 0
	if product_id in meta_dict:
		product = meta_dict[product_id]
		product_name = product['product_name']
		category = product['category']
		if len(category) > 0:
			isfound = 1
			#if product already exists: add to the current product information
			if len(query_res) > 0:
				contents = query_res[0]["contents"] + contents_new
				review_ids = query_res[0]["review_ids"]
				ratings = query_res[0]["ratings"]
				review_ids.append(review_id_new)
				ratings.append(rating_new)
				review_ending_sentence_list = query_res[0]["review_ending_sentence"]
				review_ending_sentence_new = num_sentence + review_ending_sentence_list[-1]
				review_ending_sentence_list.append(review_ending_sentence_new)
				num_reviews = query_res[0]["num_reviews"] + 1

				update_field = {
					"contents": contents,
					"review_ids": review_ids,
					"ratings": ratings,
					"review_ending_sentence": review_ending_sentence_list,
					"num_reviews": num_reviews,
					"category": category
				}
			
			# if product not in database:
			else:
				contents = contents_new
				review_ids = []
				ratings = []
				review_ending_sentence_list = []
				review_ids.append(review_id_new)
				ratings.append(rating_new)
				review_ending_sentence_list.append(num_sentence)
				num_reviews = 1
				update_field = {
					"contents": contents,
					"product_name": product_name,
					"review_ids": review_ids,
					"ratings": ratings,
					"review_ending_sentence": review_ending_sentence_list,
					"num_reviews": num_reviews,
					"category": category,
					"ft_score": {},
					"ft_senIdx": {}
				}

			query = {"product_id": product_id}
			db_product_collection.update(query, {"$set": update_field}, True)

	return isfound

	
def parse(path):
	g = gzip.open(path, 'r')
	for l in g:
		yield ast.literal_eval(l)

def construct_metadata_dict(meta_file_path, category_name):
	"""return a dictionary for product metadata"""
	metaParser = parse(meta_file_path)
	client, db = connect_to_db()
	i=0
	j=0
	meta_dict = {}
	print "building the dict for product metadata"
	for meta in metaParser:
		i+=1
		if i%1000 == 0:
			print i, j
		category = meta['categories'][0]

		if category_name in category or len(category_name) == 0:
			j += 1
			product_id = meta['asin']
			if 'title' in meta:
				product_name = meta['title']
			else:
				product_name = ""

			meta_dict[product_id]={'category': category, 'product_name':product_name}
		
	return meta_dict

def upsert_all_reviews(review_file_path, meta_dict):
	reviewParser = parse(review_file_path)
	client, db = connect_to_db()
	db_product_collection = db.product_collection

	i=0
	num_found = 0
	print "building product_collection in database"
	for review in reviewParser:
		isfound = upsert_review_for_product_id(review, db_product_collection, meta_dict)
		num_found += isfound
		i+=1
		if i%100 == 0:
			print i, num_found
	client.close()

def upsert_new_product(db_product_collection, product_id, product_name, category, contents_new, review_ids_new, ratings_new, review_ending_sentence_new, num_reviews_new, ft_senIdx, ft_score):
	"""upsert product information """
	query_res = list(db_product_collection.find({"product_id": product_id}))
	if len(query_res) > 0:
		contents = query_res[0]["contents"] + contents_new
		num_sentence = len(contents)
		review_ids = query_res[0]["review_ids"]
		ratings = query_res[0]["ratings"]
		review_ids += review_ids_new
		ratings += ratings_new
		review_ending_sentence = query_res[0]["review_ending_sentence"]
		review_ending_sentence_new = [item + review_ending_sentence[-1] for item in review_ending_sentence_new]
		review_ending_sentence += review_ending_sentence_new	
		num_reviews = query_res[0]["num_reviews"] + num_reviews_new

	elif len(query_res) == 0:
		contents = contents_new
		review_ids = review_ids_new
		ratings = ratings_new
		review_ending_sentence = review_ending_sentence_new
		num_reviews = num_reviews_new

	query = {"product_id": product_id}
	update_field = {
		"product_name": product_name,
		"category": category,
		"contents": contents,
		"review_ids": review_ids,
		"ratings": ratings,
		"review_ending_sentence": review_ending_sentence,
		"scraped_pages": [],
		"num_reviews": num_reviews,	
		"ft_senIdx": ft_senIdx,
		"ft_score": ft_score
	}
	db_product_collection.update(query, {"$set": update_field}, True)


def upsert_all_reviews_bulk(review_file_path, meta_dict):
	"""Based on the fact that a product's review is consecutive, this function bulk upsert all the reviews for one product"""
	reviewParser = parse(review_file_path)
	client, db = connect_to_db()
	db_product_collection = db.product_collection
	db_product_collection.create_index([("product_id", ASCENDING)])

	i=0
	num_found = 0
	print "building product_collection in database"
	product_id = "a"
	for review in reviewParser:
		i += 1
		if i % 1000 ==0:
			print i
		#new data:
		product_id_new = review['asin']
		contents_new = getSentencesFromReview(review['reviewText'])
		num_sentence = len(contents_new)
		review_id_new = review['reviewerID']
		rating_new = review['overall']

		# If the product id is the same, then just concatenate the field
		if product_id_new == product_id:
			contents = contents + contents_new
			review_ids.append(review_id_new)
			ratings.append(rating_new)
			review_ending_sentence.append(num_sentence + review_ending_sentence[-1])
			num_reviews += 1

		# If encountering new product: save previous product, and initialize the product variables
		elif product_id_new != product_id:
			if i > 1:
				upsert_new_product(db_product_collection, product_id, product_name, category, contents, review_ids, ratings, review_ending_sentence, num_reviews, ft_senIdx, ft_score)
			product_id = product_id_new
			product_name = []
			category = []
			if product_id in meta_dict:
				product = meta_dict[product_id]			
				if 'product_name' in product:
					product_name = product['product_name']
				if 'category' in product:
					category = product['category']		
			contents = contents_new
			review_ids = []
			ratings = []
			review_ending_sentence = []
			review_ids.append(review_id_new)
			ratings.append(rating_new)
			review_ending_sentence.append(num_sentence)
			num_reviews = 1
			ft_score = {}
			ft_senIdx = {}

	client.close()


def calculate_ft_dict_for_all_products(predictor_name):
	predictor = loadTrainedPredictor()
	client, db = connect_to_db()
	db_product_collection = db.product_collection
	cursor = db_product_collection.find()
	
	i=0
	for product in cursor:
		i+=1
		product_id = product['product_id']
		prod_contents = product['contents']
		prod_ft_score_dict, prod_ft_senIdx_dict = get_ft_dicts_from_contents(prod_contents, predictor)
		query = {"product_id": product_id}
		update_field = {
			"ft_score": prod_ft_score_dict,
			"ft_senIdx": prod_ft_senIdx_dict
		}
		db_product_collection.update(query, {"$set": update_field}, True)
		if i%10 == 0:
			print i

	client.close()

def statisitcs():
	import numpy as np
	client, db = connect_to_db()
	db_product_collection = db.product_collection
	cursor = db_product_collection.find()
	
	i=0
	total_sentence_num = 0
	total_review_num = 0
	num_review_list =[]
	num_sentence_list = []
	for product in cursor:
		i+=1
		num_review= product['num_reviews']
		num_sentence=product['review_ending_sentence'][-1]
		num_review_list.append(num_review)
		num_sentence_list.append(num_sentence)
		total_review_num += num_review
		total_sentence_num += num_sentence
	
	client.close()
	hist, binedge = np.histogram(num_sentence_list, np.max(num_sentence_list))
	print hist, binedge
	print total_sentence_num
	print np.sum(num_sentence_list)
	# for item in hist:
	# 	print item
	# for item in binedge:
	# 	print item
	# import matplotlib.pyplot as plt
	# fig = plt.figure()
	# fig.suptitle('histogram: number of reviews per product')
	# ax = fig.add_subplot(111)
	# ax.hist(num_review_list, bins=30)
	# ax.set_xlabel('number of reviews per product')
	# plt.show()



def main():
	Electronics_Review_Path = '../../Datasets/Full_Reviews/reviews_Electronics.json.gz'
	Electronics_Meta_Path = '../../Datasets/Full_Reviews/meta_Electronics.json.gz'
	category_name = []
	predictor_name = 'Word2Vec'
	
	#Construct the meta_dict that stores product information that belongs to "category_name"
	meta_dict = construct_metadata_dict(Electronics_Meta_Path, category_name)

	#Add all reviews to product_collection that belongs to "category_name"
	upsert_all_reviews_bulk(Electronics_Review_Path, meta_dict)

	#Calculate the ft_dict for all products:
	# calculate_ft_dict_for_all_products(predictor_name)


if __name__ == '__main__':
	# main()
	