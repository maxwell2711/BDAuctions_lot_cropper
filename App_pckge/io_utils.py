import os, re
from collections import defaultdict

_LOT_PATTERN = re.compile(r"(\d+)(?:\s*\(\d+\))?\.(jpg|jpeg|png)$", re.IGNORECASE)
_IDX_PAT = re.compile(r"\((\d+)\)")

def group_images_by_lot(folder: str):
    lot_dict = defaultdict(list)
    for filename in os.listdir(folder):
        m = _LOT_PATTERN.match(filename)
        if m:
            lot = m.group(1)
            lot_dict[lot].append(os.path.join(folder, filename))
    return lot_dict

def _order_index(path_or_name: str, default_idx: int):
    name = os.path.basename(path_or_name)
    m = _IDX_PAT.search(name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return default_idx
    return 0

def natural_sort_by_index(paths):
    # 6.jpg first, then 6 (1).jpg, 6 (2).jpg, ...
    return sorted(paths, key=lambda p: _order_index(p, 10**9))

def numeric_first_sort(keys):
    def keyfn(k):
        try:
            return (0, int(k))
        except ValueError:
            return (1, str(k))
    return sorted(keys, key=keyfn)