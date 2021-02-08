from backoff import Backoff
from timeit import default_timer as timer

backoff = Backoff(['rus-Cyrl', 'eng-Latn'], cedict_file=None)

start = timer()
backoff.transliterate('Съ+ешь ещё +этих soft french б+улок д+а в+ыпей tea')
end = timer()
print(end - start)