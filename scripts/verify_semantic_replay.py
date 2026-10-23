"""Compare a completed semantic experiment with its no-key cache replay."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('original', type=Path)
    parser.add_argument('replay', type=Path)
    args = parser.parse_args()
    original = read(args.original/'summary.json')
    replay = read(args.replay/'summary.json')
    assert original['status'] == replay['status'] == 'completed_semantic_experiment'
    for field in ('completed_runs','sampled_documents','validated_documents','available_documents'):
        assert original[field] == replay[field], field
    usage = replay['llm_preprocessing']
    assert usage['cached_calls'] == replay['sampled_documents']
    assert usage['uncached_responses'] == usage['uncached_total_tokens'] == 0
    compared = 0
    for task in original['tasks']:
        for mode in ('fixed','basic','enhanced'):
            rel = Path(task['directory'])/mode/'result.json'
            first, second = read(args.original/rel), read(args.replay/rel)
            # cache_hit is provenance, so annotation SHA legitimately changes.
            assert first['provenance']['input_sha256'] == second['provenance']['input_sha256']
            assert first['result'] == second['result']
            assert first['rounds'] == second['rounds']
            left = first['provenance']['annotations']
            right = second['provenance']['annotations']
            assert set(left) == set(right)
            for key in left:
                assert {k:v for k,v in left[key].items() if k!='cache_hit'} == {k:v for k,v in right[key].items() if k!='cache_hit'}
            compared += 1
    print(json.dumps({'status':'passed','compared_runs':compared,
        'cached_calls':usage['cached_calls'],'uncached_tokens':0}))


if __name__ == '__main__':
    main()
