"""Category persistence is transactionally owned by ContactStore."""
from utils.validators import clean_category

def category_options(store):
    return [category['name'] for category in store.categories()]
