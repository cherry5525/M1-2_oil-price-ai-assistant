"""진짜 Firestore 대신 쓰는 가짜 DB (테스트가 인터넷/키 없이 빠르게 돌도록).

읽은 문서 수를 db.counter["reads"]에 세어 둔다. (Firestore는 읽은 문서 수만큼 무료 한도가 줄어들기 때문)
"""
from collections import defaultdict


class Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class Ref:
    def __init__(self, store, doc_id, counter):
        self.store = store
        self.id = doc_id
        self.counter = counter

    def get(self, transaction=None):
        self.counter["reads"] += 1
        return Snap(self.id, self.store.get(self.id))

    def update(self, updates):
        self.store[self.id].update(updates)

    def delete(self):
        self.store.pop(self.id, None)


class Query:
    def __init__(self, store, counter, filters=(), order=None, descending=False, skip=0, max_items=None):
        self.store = store
        self.counter = counter
        self.filters = filters
        self.order = order
        self.descending = descending
        self.skip = skip
        self.max_items = max_items

    def _copy(self, **changes):
        params = dict(store=self.store, counter=self.counter, filters=self.filters, order=self.order,
                      descending=self.descending, skip=self.skip, max_items=self.max_items)
        params.update(changes)
        return Query(**params)

    def where(self, field, op, value):
        return self._copy(filters=self.filters + ((field, op, value),))

    def order_by(self, field, direction="ASCENDING"):
        return self._copy(order=field, descending=(direction == "DESCENDING"))

    def offset(self, n):
        return self._copy(skip=n)

    def limit(self, n):
        return self._copy(max_items=n)

    @staticmethod
    def _match(data, field, op, value):
        actual = data.get(field)
        if op == "==":
            return actual == value
        if actual is None:
            return False
        return {">=": actual >= value, "<=": actual <= value}[op]

    def stream(self):
        items = [(i, d) for i, d in self.store.items()
                 if all(self._match(d, f, op, v) for f, op, v in self.filters)]
        if self.order:
            items.sort(key=lambda kv: str(kv[1].get(self.order)), reverse=self.descending)
        items = items[self.skip:]
        if self.max_items is not None:
            items = items[:self.max_items]
        self.counter["reads"] += len(items)
        return iter([Snap(i, d) for i, d in items])

    def get(self):
        return list(self.stream())


class Collection(Query):
    def __init__(self, store, counter):
        super().__init__(store, counter)

    def document(self, doc_id):
        return Ref(self.store, doc_id, self.counter)

    def add(self, data):
        doc_id = f"doc{len(self.store) + 1}"
        self.store[doc_id] = dict(data)
        return None, Ref(self.store, doc_id, self.counter)


class FakeTransaction:
    """진짜 트랜잭션처럼 동작하지는 않고, 트랜잭션 경로로 쓰기가 일어났는지만 기록한다."""

    def __init__(self, db):
        self.db = db

    def update(self, ref, updates):
        self.db.transaction_updates += 1
        ref.update(updates)


class FakeDB:
    def __init__(self):
        self.collections = defaultdict(dict)  # 컬렉션 이름 -> {문서 id: 데이터}
        self.transaction_updates = 0
        self.counter = {"reads": 0}           # Firestore에서 읽은 문서 수

    def collection(self, name):
        return Collection(self.collections[name], self.counter)

    def transaction(self):
        return FakeTransaction(self)

    # ---- 테스트 도우미 ----
    def seed_prices(self, rows):
        """rows: (날짜, 가격) 또는 (날짜, 가격, 메모) 목록"""
        for i, row in enumerate(rows):
            date, value, *rest = row
            self.collections["data"][f"p{len(self.collections['data'])}_{i}"] = {
                "date": date, "value": value, "memo": rest[0] if rest else ""}
