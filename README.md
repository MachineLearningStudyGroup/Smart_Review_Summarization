# Smart_Review_Summarization
An automatic summarization tool for product reviews

## Dependencies management

### Anaconda environment creation
```
conda env create
```

### `amazon_scraper` installation
```
pip install amazon_scraper
```

### `nltk_data/tokenizers` and `nltk_data/corpora`
```
python
nltk.download()
```
choose `punkt` for tokenizer, `sentiwordnet` and `wordnet` for corpora.

### `MongoDB` configuration
To enable fast query and update with product_id, enter
```
db.product_collection.createIndex({"product_id":1})
```
in MongoDB shell, to index the "product_id" field. 

## Installation
Append package directory `/path/to/Smart_Review_Summarization` into PYTHONPATH

## Run
```
source activate srs
```
