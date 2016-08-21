import numpy as np
import operator
from srs import settings
from utilities import tokenize, loadUsefulTrainingData, loadScraperDataFromDB, Sentence, AspectPattern
import json
import os
import re
import copy
import word2vec
from nltk.corpus import wordnet as wn

def eval_f_vec(token_list,wordlist_dict):
    """
    token_list: a list of tokens from content
    returns f_vec in the form of dictionary
    """
    len_word = max(len(token_list),1)*1.0;
    f_vec = copy.deepcopy(wordlist_dict) #speed up by putting copy and reset outside
    #reset to zero 
    for key in f_vec.keys():
    	for i in range(len(f_vec[key])):
    		f_vec[key][i][1]=0

    for key in wordlist_dict.keys():
        for i in range(len(wordlist_dict[key])):
            count = token_list.count(wordlist_dict[key][i][0])
            f_vec[key][i][1]=(count/len_word)
    
    #returns a dictionary with frequency 
    return f_vec

def cond_prob(f_vec,wordlist_dict,const_wt=False):
	'''
	only the numerator since we only need it for prediction
	'''
	score_dict = dict.fromkeys(f_vec, 0)
	for key in f_vec.keys():
		dot_product = 0.0
		for i in range(len(wordlist_dict[key])):
			if const_wt:
				dot_product += np.exp(f_vec[key][i][1]*1)
			else: 
				dot_product += np.exp(f_vec[key][i][1]*wordlist_dict[key][i][1])

		score_dict[key] = dot_product/len(wordlist_dict[key]) # min score is 1

	print score_dict
	return score_dict

def sentence_prediction(sentence,wordlist_dict,w2v_model,thres):
	'''
	predict aspect based on the score_dict. The default is the maximum
	'''
	#tokenize the sentence if not already
	if not sentence.tokens:
		# not tokenize before 
		token_list = tokenize(sentence.content, stem=False)
		sentence.tokens = token_list
	else:
		token_list = sentence.tokens

	f_vec = eval_f_vec(token_list,wordlist_dict)
	score_dict = cond_prob(f_vec,wordlist_dict)
	# print f_vec
	predicted_aspect = max(score_dict.iteritems(), key=operator.itemgetter(1))[0]
	if score_dict[predicted_aspect] == 1: # no key word overlap
		# get another list of token from definition
		token_list_expand = createTokenDefinition(token_list)
		f_vec_expand = eval_f_vec(token_list_expand,wordlist_dict)
		score_dict_expand = cond_prob(f_vec_expand,wordlist_dict,const_wt=True) 
		predicted_aspect = max(score_dict_expand.iteritems(), key=operator.itemgetter(1))[0]
		if score_dict_expand[predicted_aspect] == 1:
			#call word2vec similarity 
			score_dict_w2v = word2vec_predict(token_list_expand,wordlist_dict,w2v_model)
			predicted_aspect = max(score_dict_w2v.iteritems(), key=operator.itemgetter(1))[0]
			if score_dict_w2v[predicted_aspect] < thres:
				predicted_aspect = 'no feature'

	sentence.static_aspect = predicted_aspect

def word2vec_predict(token_list,wordlist_dict,w2v_model):
	s_vec = eval_s_vec(token_list,wordlist_dict,w2v_model)
	#post process to return an aspect of most similar
	score_dict_w2v = dict.fromkeys(s_vec, 0)
	# 1. get the maximum of each seed without weight (weight doesn't do well)
	for key in s_vec.keys():
		dot_product = 0.0
		similarity_wt_max = 0
		for i in range(len(wordlist_dict[key])):
			similarity_wt = s_vec[key][i][1]
			if similarity_wt > similarity_wt_max:
				similarity_wt_max = similarity_wt
		score_dict_w2v[key] = similarity_wt_max 

	print score_dict_w2v
	return score_dict_w2v

def eval_s_vec(token_list,wordlist_dict,w2v_model):
	# create cosine similarity matrix
	s_vec = copy.deepcopy(wordlist_dict) #speed up by putting copy and reset outside
	#reset to zero 
	for key in s_vec.keys():
		for i in range(len(s_vec[key])):
			s_vec[key][i][1]=0

	for key in wordlist_dict.keys():
	    for i in range(len(wordlist_dict[key])):
	    	v_seed = w2v_model[wordlist_dict[key][i][0]]
	    	similarity = []
	    	for token in token_list:
	    		if token in w2v_model:
	    			v_token = w2v_model[token]
	    			# similarity.append(np.linalg.norm(v_token-v_seed))
	    			similarity.append(np.dot(v_token,v_seed))
	    		else: 
	    			similarity.append(0)
	    	max_idx = similarity.index(max(similarity))
	    	# print (token_list[max_idx],wordlist_dict[key][i][0],similarity[max_idx])
	    	s_vec[key][i][1] = max(similarity)

	return s_vec

def getPredictorDataFilePath(filename):
	predictor_datafile_path = os.path.join(settings["predictor_data"], filename)
	if os.path.exists(predictor_datafile_path):
		return predictor_datafile_path
	else:
		raise Exception("{} is not found!".format(predictor_datafile_path))

def createTokenDefinition(token_list):
	token_list_expand = []
	for token in token_list:
		def_noun = wn.synsets(token,pos=wn.NOUN)
		def_adj = wn.synsets(token,pos=wn.ADJ)
		if len(def_noun) > 0:
			def_string = def_noun[0].definition()
		elif len(def_adj) > 0: 
			def_string = def_adj[0].definition()

		token_list_expand = token_list_expand + tokenize(def_string,stem=False,entire=False)#entire => larger set of stopword
	print token_list_expand
	return token_list_expand

if __name__ == '__main__':
	static_traning_data_dir = settings["static_training_data"]

	# sentences = loadTrainingData(static_traning_data_dir)
	sentences = loadUsefulTrainingData(static_traning_data_dir)

	# load wordlist dictionary from Tailin
	wordlist_dict_path = os.path.join(settings["predictor_data"], 'wordlist_dict_camera_wt.txt')
	wordlist_dict = json.load(open(wordlist_dict_path, 'r'))

	# load word2vec model
	model_filename = 'text8.bin'
	model_file_path = getPredictorDataFilePath(model_filename)
	w2v_model = word2vec.load(model_file_path)  #load word2vec model

	#begin testing
	# sentence = sentences[122] # change index for different sentences 
	# sentence = Sentence('I find it easy to operate.')
	# content = "Obviously, if you're a serious photographer, this is not the camera for you, but for me, it's great."
	# content = 'After several hours of use, the flickering seemed to mostly go away, but not entirely.' #success
	# content = "I know it's a lot to ask from an entry-level camera, but even for basic use I am not comfortable with a camera that seems to miss 2 out of every 3 shots." #success
	content = "I found the menu to be clunky, and many basic features like shutter and aperture settings, manual focus (or at least a user-selected Macro mode) were either lacking entirely or buried in some menu that I couldn't find when I needed it"
	sentence = Sentence(content)
	print sentence.content
	sentence_prediction(sentence,wordlist_dict,w2v_model,0.85)
	print sentence.static_aspect
	print sentence.labeled_aspects

	# test createTokenDefinition
	# token_list = [u'week', u'test', u'run', u'every', u'situation', u'night', u'action', u'inside', u'outside', u'object', u'people']
	# token_list_expand = createTokenDefinition(token_list)
	# print token_list_expand

