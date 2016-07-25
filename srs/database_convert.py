from pymongo import MongoClient
from utilities import getSentencesFromReview
from srs_local import get_ft_dicts_from_contents
from predictor import loadTrainedPredictor
import gzip
import ast

def connect_to_db():
	client = MongoClient('localhost', 27017)
	db = client['srs']
	return client, db

def query_for_product_metadata(product_id, db_product_metadata):
	#query the product_metadata collection for product_id's metadata information
	query_metadata = list(db_product_metadata.find({"product_id": product_id}))
	product_name = []
	category = []
	if len(query_metadata) >0:
		if 'product_name' in query_metadata[0]:
			product_name = query_metadata[0]['product_name']
		if 'category' in query_metadata[0]:
			category = query_metadata[0]['category']

	return product_name, category

def upsert_review_for_product_id(review, db_product_collection, db_product_metadata):
	#For each review, if it belongs to the category indicated by "category_name", add it to the product_collection in db
	product_id = review['asin']
	query_res = list(db_product_collection.find({"product_id": product_id}))

	contents_new = getSentencesFromReview(review['reviewText'])
	num_sentence = len(contents_new)
	review_id_new = review['reviewerID']
	rating_new = review['overall']

	query_review = list(db_product_collection.find({"$and":[{"product_id": product_id},{"review_ids": review_id_new}]}))
	isfound = 0
	if len(query_review) == 0:
		product_name, category = query_for_product_metadata(product_id, db_product_metadata)
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

def insert_product_metadata(product_metadata, category_name, db_product_metadata):
	#input: product_metadata: metadata from the file parser; category_name: the category we want to add to the product_metadata collection
	#create an item in the db's product_metadata collection, if the current product_metadata belongs to the category indicated by "category_name"
	product_id = product_metadata['asin']
	category = product_metadata['categories'][0]

	if 'title' in product_metadata:
		product_name = product_metadata['title']
	else:
		product_name = ""
	isCategory = -1
	for single_category in category:
		if single_category.find(category_name) > -1:
			isCamera = 1

	if isCategory == 1:
		query = {"product_id": product_id}
		update_field = {
		"product_name": product_name,
			"category": category
		}
		db_product_metadata.update(query, {"$set": update_field}, True)
	
def parse(path):
	g = gzip.open(path, 'r')
	for l in g:
		yield ast.literal_eval(l)

def construct_product_metadata_collection(meta_file_path, category_name):
	metaParser = parse(meta_file_path)
	client, db = connect_to_db()
	db_product_metadata = db.product_metadata

	i=0
	for meta in metaParser:
		insert_product_metadata(meta, category_name, db_product_metadata)
		i+=1
		if i%1000 == 0:
			print i

def upsert_all_reviews(review_file_path):
	reviewParser = parse(review_file_path)
	client, db = connect_to_db()
	db_product_collection = db.product_collection
	db_product_metadata = db.product_metadata

	i=0
	num_found = 0
	for review in reviewParser:
		isfound = upsert_review_for_product_id(review, db_product_collection, db_product_metadata)
		num_found += isfound
		i+=1
		if i%100 == 0:
			print i, num_found
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
	category_name = "Digital Cameras"
	predictor_name = 'Word2Vec'
	
	#Construct the product_metadata collection in db that belongs to "category_name"
	# construct_product_metadata_collection(Electronics_Meta_Path, category_name)

	#Add all reviews to product_collection that belongs to "category_name"
	# upsert_all_reviews(Electronics_Review_Path)

	#Calculate the ft_dict for all products:
	calculate_ft_dict_for_all_products(predictor_name)


if __name__ == '__main__':
	# main()
	