
from external.potts_tokenizer import PottsTokenizer
import nltk

def tokenize(string):
	"""
	INPUT: string
	OUTPUT: a list of words
	"""
	tokenizer = PottsTokenizer(preserve_case=False)
	return tokenizer.tokenize(string)

class Sentence(object):

	def __init__(self, content, tokens=[], aspects='', sentiment=None):
		self.content = content
		self.tokens = tokens
		self.aspects = aspects
		self.sentiment = sentiment
		self.pos_tagged_tokens = []
		self.dynamic_aspects = []
		

	def tokenize(self):
		self.tokens = tokenize(self.content)

	def pos_tag(self):
		# if not tokenized do that first
		if not self.tokens:
			self.tokenize()
		# pos tagging
		self.pos_tagged_tokens = nltk.pos_tag(self.tokens)

	def matchDaynamicAspectPatterns(self, patterns):
		"""
		INPUT: a list of patterns
		OUTPUT: figure out the dynamic aspects matching the patterns
		"""
		STOPWORDS = set(nltk.corpus.stopwords.words('english'))

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
				print 'aspect candidate found by {0}: {1}'.format(pattern.name, aspectCandidate)
				if aspectCandidate != '' and aspectCandidate not in self.dynamic_aspects:
					self.dynamic_aspects.append(aspectCandidate)

class AspectPattern(object):

	def __init__(self, name, structure, aspectTagIndices):
		self.name = name
		self.structure = structure
		self.aspectTagIndices = aspectTagIndices

class Review(object):

	def __init__(self, title=None, sentences=[], star=None):
		self.title = title
		self.sentences = sentences
		self.star = star


class Product(object):

	def __init__(self, name, reviews=[]):
		self.name = name
		self.reviews = reviews

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
				sentence = Sentence(content=content, aspects=aspects)
				sentences.append(sentence)
			review = Review(title=title, sentences=sentences)
			reviews.append(review)

		self.reviews = reviews



	

		
