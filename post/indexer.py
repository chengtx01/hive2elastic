import logging
import multiprocessing as mp
import sys
import time

import configargparse
import elasticsearch
from elasticsearch import helpers
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .es_helpers import make_index_config, doc_from_row
from .util import chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hive2elastic')

# disable elastic search's confusing logging
logging.getLogger('elasticsearch').setLevel(logging.CRITICAL)


parser = configargparse.get_arg_parser()

parser.add('--db-url', env_var='DB_URL', required=True, help='hive database connection url')
parser.add('--es-url', env_var='ES_URL', required=True, help='elasticsearch connection url')
parser.add('--es-index', env_var='ES_INDEX', help='elasticsearch index name', default='hive_posts')
parser.add('--es-type', env_var='ES_TYPE', help='elasticsearch type name', default='posts')
parser.add('--bulk-size', env_var='BULK_SIZE', type=int, help='number of records in a single loop', default=500)
parser.add('--max-workers', type=int, env_var='MAX_WORKERS', help='max workers', default=2)
parser.add('--max-bulk-errors', type=int, env_var='MAX_BULK_ERRORS', help='', default=5)

args = parser.parse_args()

global conf

conf = vars(args)

es = None
bulk_errors = 0

def convert_post(row):
    return doc_from_row(row, conf['es_index'], conf['es_type'])


def run():
    global conf, es, index_name, bulk_errors

    try:
        db_engine = create_engine(conf['db_url'])
        db_engine.execute("SELECT post_id FROM __h2e_posts LIMIT 1")
    except OperationalError:
        raise Exception("Could not connected: {}".format(conf['db_url']))
    except ProgrammingError:
        raise Exception("__h2e_posts table not exists in database")

    es = elasticsearch.Elasticsearch(conf['es_url'])

    if not es.ping():
        raise Exception("Elasticsearch server not reachable")

    index_name = conf['es_index']
    index_type = conf['es_type']

    try:
        es.indices.get(index_name)
    except elasticsearch.NotFoundError:
        logger.info('Creating new index {}'.format(index_name))
        index_config = make_index_config(index_type)
        es.indices.create(index=index_name, body=index_config)

    logger.info('Starting indexing')

    while True:
        start = time.time()

        sql = '''SELECT post_id, author, permlink, category, depth, children, author_rep,
                 flag_weight, total_votes, up_votes, title, img_url, payout, promoted,
                 created_at, payout_at, updated_at, is_paidout, is_nsfw, is_declined,
                 is_full_power, is_hidden, is_grayed, rshares, sc_hot, sc_trend, sc_hot,
                 body, votes,  json FROM hive_posts_cache
                 WHERE post_id IN (SELECT post_id FROM __h2e_posts ORDER BY post_id ASC LIMIT :limit)
                '''

        posts = db_engine.execute(text(sql), limit=conf['bulk_size']).fetchall()
        db_engine.dispose()

        if len(posts) == 0:
            time.sleep(0.5)
            continue

        pool = mp.Pool(processes=conf['max_workers'])
        index_data = pool.map_async(convert_post, posts).get()
        pool.close()
        pool.join()

        try:
            helpers.bulk(es, index_data)
            bulk_errors = 0
        except helpers.BulkIndexError as ex:
            bulk_errors += 1
            logger.error("BulkIndexError occurred. {}".format(ex))

            if bulk_errors >= conf['max_bulk_errors']:
                sys.exit(1)

            time.sleep(1)
            continue

        post_ids = [x.post_id for x in posts]
        chunked_id_list = list(chunks(post_ids, 200))

        for chunk in chunked_id_list:
            sql = "DELETE FROM __h2e_posts WHERE post_id IN :ids"
            db_engine.execute(text(sql), ids=tuple(chunk))

        end = time.time()
        logger.info('{} indexed in {}'.format(len(posts), (end - start)))


def main():

    run()

if __name__ == "__main__":
    main()
