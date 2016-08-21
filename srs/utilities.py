
from external.potts_tokenizer import PottsTokenizer
import nltk
import json
import string
import os
from nltk.stem.porter import PorterStemmer
from nltk.stem.snowball import SnowballStemmer
from database import select_for_product_id
import re

def getSentencesFromReview(reviewContent):
    """
    INPUT: a single review consist of serveral sentences
    OUTPUT: a list of single sentences
    """
    sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')
    sentences = sent_detector.tokenize(reviewContent)
    # split agglomerated sentences
    for m in range(len(sentences)):
        subsentences = sentences[m].split('.')
        new_sentences = []
        new_subsen = subsentences[0]
        for n in range(1,len(subsentences)):
            if subsentences[n] and (subsentences[n][0] in string.ascii_uppercase):
                new_subsen += '.'
                new_sentences.append(new_subsen)
                new_subsen = subsentences[n]
            else:
                new_subsen += '.' + subsentences[n]
        new_sentences.append(new_subsen)
        sentences[m] = new_sentences
    # collect all the single sentence into final_sentence list
    final_sentences = []
    for sentence in sentences:
        if isinstance(sentence, list):
            final_sentences.extend(sentence)
        else:
            final_sentences.append(sentence)
    return final_sentences

def tokenize(string, stem=True, entire=False):
    """
    INPUT: string
    OUTPUT: a list of words
    """
    string = string.replace("/", " ")
    string = string.replace("-", " ")
    tokenizer = PottsTokenizer(preserve_case=False)
    token_list = tokenizer.tokenize(string)
    punctuation = re.compile(r'[-.?!,":;$/*()|0-9]') # remove these punctuations and number 
    token_list = [punctuation.sub("", word) for word in token_list]  
    token_list = filter(None, token_list) #filters empty   

    #filter out stopwords 
    STOPWORDS = set(nltk.corpus.stopwords.words('english'))
    STOPWORDS.update(('nikon','would','does','got',"doesn't",'well','somehow', 'someone', 'something', 'sometime', 'sometimes', 'somewhere'))
    if entire:
        # if need a larger set
        stopwords_entire_list = loadEntireStopWord()
        STOPWORDS.update(set(stopwords_entire_list))
    token_list = [word for word in token_list if word not in STOPWORDS]

    #stemmer 
    if stem:
        stemmer = SnowballStemmer("english")
        token_stem_list = [stemmer.stem(token) for token in token_list]
        token_list = token_stem_list

    return token_list

def loadUsefulTrainingData(static_training_data_dir):
    import os
    sentences = []
    for data_file in os.listdir(static_training_data_dir):
        if data_file.endswith('labeled.txt'):
            sentences.extend(loadTrainingDataFromFile(os.path.join(static_training_data_dir, data_file)))
    
    useful_sentences = []
    for sent in sentences:
        if sent.labeled_aspects not in ['no feature', 'other features']:
            useful_sentences.append(sent)

    return useful_sentences

def loadTrainingData(static_training_data_dir):
    import os
    sentences = []
    for data_file in os.listdir(static_training_data_dir):
        if data_file.endswith('labeled.txt'):
            sentences.extend(loadTrainingDataFromFile(os.path.join(static_training_data_dir, data_file)))
    return sentences

def loadTrainingDataFromFile(file_name): 
    with open(file_name) as f:
        sentences =[]
        for line in f.readlines():
            line_splitted = line.split('***')
            sentences.append(Sentence(content=line_splitted[1],labeled_aspects=line_splitted[0]))
    
    for sent in sentences:
        if sent.labeled_aspects in ['other features']:
            sent.labeled_aspects = 'no feature'

    return sentences 

def loadScraperDataFromFile(file_name): 
    with open(file_name) as f:
        sentences =[]
        for line in f.readlines():
            if line != "\n":
                sentences.append(Sentence(content=line))
    return sentences 

def loadScraperDataFromDB(product_id): 
    query_res = select_for_product_id(product_id)
    if len(query_res) > 0:
        return query_res[0]["contents"], query_res[0]["ft_score"], query_res[0]["ft_senIdx"]
    else:
        return [], {}, {}

def loadEntireStopWord():
    '''
    load from txt file
    return a list of stopwords
    '''
    with open("predictor_data/entire_stopword.txt", "r") as filestream:
        for line in filestream:
            line = line.replace(" ","")
            stopwords_entire_list = line.split(",")
    return stopwords_entire_list

        
class Sentence(object):
    def __init__(self, content, tokens=[], labeled_aspects='', sentiment=None, word2vec_features_list=[]):
        self.content = content
        self.tokens = tokens
        if not self.tokens:
            self.tokens = []
        self.labeled_aspects = labeled_aspects
        self.sentiment = sentiment
        self.pos_tagged_tokens = []
        self.static_aspect = None
        self.score = 0.0
        self.word2vec_features_list = word2vec_features_list
        

    def tokenize(self, stem=True):
        self.tokens = tokenize(self.content, stem=stem)

    def pos_tag(self, stem=True):
        # if not tokenized do that first
        if not self.tokens:
            self.tokenize(stem)
        # pos tagging
        self.pos_tagged_tokens = nltk.pos_tag(self.tokens)


    def word2vec_matchDaynamicAspectPatterns(self, word2vec_patterns, if_accept_same_word = 1):
        """
        INPUT: a list of patterns
        OUTPUT: figure out the dynamic aspects matching the patterns
        """
        STOPWORDS = set(nltk.corpus.stopwords.words('english'))
        patterns_num=len(word2vec_patterns)
        self.word2vec_features_list=[[] for i in range(patterns_num)]

        for i in range(patterns_num):
            patterns=word2vec_patterns[i]
            for pattern in patterns:
                chunkParser = nltk.RegexpParser(pattern.structure)
                if not self.pos_tagged_tokens:
                    self.pos_tag()
                
                chunked = chunkParser.parse(self.pos_tagged_tokens)
                for subtree in chunked.subtrees(filter=lambda t: t.label() == pattern.name):
                    aspectCandidateWords = []
                    for idx in pattern.aspectTagIndices:
                        aspectCandidateWord = subtree[idx][0]
                        if aspectCandidateWord in STOPWORDS:
                            aspectCandidateWords = []
                            break
                        else:
                            aspectCandidateWords.append(aspectCandidateWord)
                    aspectCandidate = ' '.join(aspectCandidateWords)
                    if if_accept_same_word == 1:
                        if aspectCandidate != '':
                            self.word2vec_features_list[i].append(aspectCandidate)
                    elif if_accept_same_word == 0:
                        if aspectCandidate != '' and aspectCandidate not in self.word2vec_features_list[i]:
                            self.word2vec_features_list[i].append(aspectCandidate)


class AspectPattern(object):

    def __init__(self, name, structure, aspectTagIndices):
        self.name = name
        self.structure = structure
        self.aspectTagIndices = aspectTagIndices

class Review(object):

    def __init__(self, title=None, sentences=None, star=None):
        self.title = title
        self.sentences = sentences
        if not self.sentences:
            self.sentences = []
        self.star = star


class Product(object):

    def __init__(self, name, reviews=None):
        self.name = name
        self.reviews = reviews
        if not self.reviews:
            self.reviews = []

    def loadReviewsFromTrainingFile(self, reviewTrainingFile):
        """
        INPUT: review training file containing multiple reviews for the product
        OUTPUT: create `reviews` list for product
        """
        raw_review_list = []
        start_flag = False
        with open(reviewTrainingFile, 'rb') as f:
            for line in f.readlines():
                if line.startswith('[t]'):
                    start_flag = True
                    raw_review_list.append([line])
                elif start_flag:
                    raw_review_list[-1].append(line)

        # create reviews attribute
        reviews = []
        for raw_review in raw_review_list:
            title = raw_review[0].split('[t]')[1].strip()
            sentences = []
            for raw_sentence in raw_review[1:]:
                aspects = [raw_sentence.split('##')[0]] ## need regexp to further refine the aspect
                content = raw_sentence.split('##')[1]
                sentence = Sentence(content=content, labeled_aspects=aspects)
                sentences.append(sentence)
            review = Review(title=title, sentences=sentences)
            reviews.append(review)

        self.reviews = reviews

    def loadReviewsFromJsonFile(self, reviewJsonFile):
        """
        INPUT: review json file containing multiple reviews for the product
        OUTPUT: create `reviews` list for product
        """
        f = open(reviewJsonFile, 'r')
        raw_reviews = json.load(f)
        sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')

        reviews = []
        for raw_review in raw_reviews['Reviews']:
            title = raw_review['Title']
            sentences_str = sent_detector.tokenize(raw_review['Content'])
            # split agglomerated sentences
            for m in range(len(sentences_str)):
                subsentences_str = sentences_str[m].split('.')
                new_sentences = []
                new_subsen = subsentences_str[0]
                for n in range(1,len(subsentences_str)):
                    if subsentences_str[n] and (subsentences_str[n][0] in string.ascii_uppercase):
                        new_subsen += '.'
                        new_sentences.append(new_subsen)
                        new_subsen = subsentences_str[n]
                    else:
                        new_subsen += '.' + subsentences_str[n]
                new_sentences.append(new_subsen)
                sentences_str[m] = new_sentences
            # collect all the single sentence into final_sentence list
            final_sentences_str = []
            for sentence_str in sentences_str:
                if isinstance(sentence_str, list):
                    final_sentences_str.extend(sentence_str)
                else:
                    final_sentences_str.append(sentence_str)
            
            # create sentences
            sentences = []
            for final_sentence_str in final_sentences_str:
                sentence = Sentence(content=final_sentence_str)
                sentences.append(sentence)
            review = Review(title=title, sentences=sentences)
            reviews.append(review)

        self.reviews = reviews

    

        
