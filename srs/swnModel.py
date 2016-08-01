from nltk.corpus import sentiwordnet as swn
from collections import defaultdict
import numpy as np

def get_sentiment_score(ls):
    '''
    input type sentence
    this method estimate a score for the sentence based on the swn model 
    '''
    from nltk.tokenize import word_tokenize
    import re
    word_list = word_tokenize(ls.content)
    punctuation = re.compile(r'[-.?!,":;()|0-9]') # remove these punctuations and number 
    word_list = [punctuation.sub("", word) for word in word_list]  
    word_list = filter(None, word_list) #filters empty         
    ls.tokens = word_list

    pos_score = 0.0
    neg_score = 0.0
    num_valid_word = 0.1
    for w in word_list:
        try:
            res = swn.senti_synsets(w)
            pos_score += res[0]._pos_score
            neg_score += res[0]._neg_score
            num_valid_word += 1
        except:
            pass
            
    ls.score = (pos_score - neg_score)/num_valid_word
    
    """
    documentation on swn: http://www.nltk.org/_modules/nltk/corpus/reader/sentiwordnet.html
    """
def get_sentiment_score_for_sentences(sentences):

    for sentence in sentences:
        get_sentiment_score(sentence)

def get_ftScore_ftSenIdx_dicts(sentences, start_idx = 0, forbidden_feature='no feature'):
    '''
    sentences: a list of sentence object
    staticPredictor object
    return a list of individual score for each static feature via a dictionary
    '''
    ft_score_dict = defaultdict(list)
    ft_senIdx_dict = defaultdict(list)
    for idx, sentence in enumerate(sentences):
        ft = sentence.static_aspect
        if not ft == forbidden_feature:
            ft_score_dict[ft].append(sentence.score)
            ft_senIdx_dict[ft].append(idx + start_idx)

    return ft_score_dict, ft_senIdx_dict
