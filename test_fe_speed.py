import time
import sys
import os
import logging

os.environ['PADDLEOCR_LOGGING_LEVEL'] = 'ERROR'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stdout)

sys.path.insert(0, '.')
from ml.src.extraction.hybrid_engine import HybridExtractor

engine = HybridExtractor()

t0 = time.time()
result = engine.extract_from_files(
    {'FE': 'Layout 1.pdf'},
    shipment_id='test'
)
elapsed = time.time() - t0

print(f'\nTotal time: {elapsed:.1f}s')
fe_goods = result.entities.form_e_goods
print(f'FE goods count: {len(fe_goods)}')
for g in fe_goods[:3]:
    print(f'  {g.hs_code} | {g.quantity} {g.unit} | {g.description[:60]}')
if len(fe_goods) > 3:
    print('  ...')
for g in fe_goods[-2:]:
    print(f'  {g.hs_code} | {g.quantity} {g.unit} | {g.description[:60]}')
