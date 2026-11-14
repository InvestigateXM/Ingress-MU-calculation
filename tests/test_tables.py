import json
import numpy as np
import pytest
from mu_calculator import tables
from mu_calculator.geometry import Grump, density


def test_atomic_table_and_invalidation(tmp_path, monkeypatch):
    folder = tmp_path / "bil"
    folder.mkdir()
    header = folder / "aaaup00ag.hdr"
    header.write_text("NROWS 1\nNCOLS 1\nULXMAP 0.004166666666666667\nULYMAP 0.004166666666666667\n")
    raster = folder / "aaaup00ag.bil"
    np.array([7], dtype="<f4").tofile(raster)
    monkeypatch.setattr(tables, "COUNT", 2)
    a = tables.ensure_tables(folder, workers=1)[6]
    assert isinstance(a, np.memmap)
    g = Grump(str(folder))
    for index in range(2):
        cid = (2 * index + 1) << 48
        assert a[index].tobytes() == np.float64(density(g, cid)).tobytes()
    assert tables.load_table(folder) is not None
    np.array([9], dtype="<f4").tofile(raster)
    assert tables.load_table(folder) is None
    b = tables.ensure_tables(folder, workers=1)[6]
    assert len(b) == 2
    info = json.loads(tables.table_path(folder).read_text())
    assert info["bytes"] == 144


def test_table_lookup():
    for i in (0, 4095, 4096, 24575):
        assert tables.lookup(np.arange(24576, dtype=float), (2*i+1)<<48) == i

@pytest.mark.parametrize("value", ["5", "12", "6.0", "", "six", "7e0", "9"*5000, 7.5, True])
def test_invalid_max_level(value):
    with pytest.raises(ValueError, match="MU_TABLE_MAX_LEVEL.*6.*11"):
        tables.max_level(value)


def test_max_level_environment(monkeypatch):
    monkeypatch.delenv("MU_TABLE_MAX_LEVEL", raising=False)
    assert tables.max_level() == 6
    assert tables.max_level(" 11 ") == 11
    monkeypatch.setenv("MU_TABLE_MAX_LEVEL", "9")
    assert tables.max_level() == 9


def test_index_all_levels():
    import s2sphere
    rng = np.random.default_rng(21)
    for level in range(6, 12):
        size = 6 * 4**level
        for index in [0, size-1, *(face*4**level for face in range(6)), *rng.integers(0, size, 100)]:
            cid = (2*int(index)+1) << (60-2*level)
            assert s2sphere.CellId(cid).level() == level
            assert cid >> (61-2*level) == index
        # An IJ payload must be explicitly reordered to Hilbert order.
        parent = s2sphere.CellId.from_face_pos_level(1, 0, 6)
        raw = np.arange(512*512, dtype=float).reshape(512, 512)
        values = tables.tile_values(parent, raw, level)
        for offset, child in enumerate(parent.children(level)):
            assert tables.lookup(values, child.id() - parent.child_begin(level).id() + (1 << (60-2*level))) == values[offset]


def test_repack_bit_identity():
    raw = np.random.default_rng(81).lognormal(0, 12, (512, 512))
    naive_differs = False
    for level in range(6, 12):
        n = 1 << (level-6)
        q = 512//n
        actual = tables.repack(raw, level)
        expected = np.array([[raw[i*q:(i+1)*q,j*q:(j+1)*q].copy().ravel().mean()
                              for j in range(n)] for i in range(n)])
        assert np.array_equal(actual.view('u8'), expected.view('u8'))
        naive_differs |= not np.array_equal(actual.view('u8'), raw.reshape(n,q,n,q).mean(axis=(1,3)).view('u8'))
    assert naive_differs


def test_incremental_manifest_and_corruption(tmp_path, monkeypatch):
    folder = tmp_path/'bil'
    folder.mkdir()
    (folder/'aaaup00ag.hdr').write_text('NROWS 1\nNCOLS 1\nULXMAP 0\nULYMAP 0\n')
    np.array([7], dtype='<f4').tofile(folder/'aaaup00ag.bil')
    monkeypatch.setattr(tables, 'COUNT', 2)
    tables.ensure_tables(folder, workers=1, maximum=6)
    old = tables.table_path(folder,6).read_bytes()
    tables.ensure_tables(folder, workers=1, maximum=8)
    assert tables.table_path(folder,6).read_bytes() == old
    before = {l: tables.table_path(folder,l).read_bytes() for l in (6,7,8)}
    assert list(tables.ensure_tables(folder, workers=1, maximum=6)) == [6]
    assert all(tables.table_path(folder,l).read_bytes() == v for l,v in before.items())
    tables.table_path(folder,7).unlink()
    tables.ensure_tables(folder, workers=1, maximum=8)
    assert tables.table_path(folder,8).read_bytes() == before[8]
    info = json.loads(tables.table_path(folder,7).read_text())
    path = tmp_path/info['file']
    a = np.load(path, mmap_mode='r+')
    a[0] = 123
    a.flush()
    assert tables.load_table(folder,level=7) is None
    tables.ensure_tables(folder, workers=1, maximum=8)
    assert tables.table_path(folder,8).read_bytes() == before[8]
    info['file'] = '../escape.npy'
    tables.table_path(folder,7).write_text(json.dumps(info))
    assert tables.load_table(folder,level=7) is None
    signature = tables.fingerprint(folder)
    monkeypatch.setattr(tables, 'SAMPLING_VERSION', 'changed')
    assert tables.fingerprint(folder) != signature
    assert tables.load_table(folder,level=8) is None


def test_partial_tables_fall_back(monkeypatch):
    import s2sphere
    from mu_calculator import geometry
    g = Grump('/nonexistent')
    cid = s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(52,10)).parent(7).id()
    monkeypatch.setattr(g, 'sample', lambda *args: np.array([42.0]))
    g.density_table = {6: np.zeros(24576)}
    assert density(g,cid) == 42
    g.density_table[7] = np.ones(98304)
    assert density(g,cid) == 1
    assert density(g,cid,14) == 42


def test_validation_before_download(monkeypatch):
    from mu_calculator import __main__ as cli
    monkeypatch.setenv('MU_TABLE_MAX_LEVEL', '12')
    monkeypatch.setattr('sys.argv', ['mu_calculator', 'calc'])
    monkeypatch.setattr(cli, 'ensure_data', lambda folder: pytest.fail('download before validation'))
    with pytest.raises(ValueError, match='MU_TABLE_MAX_LEVEL'):
        cli.main()


def test_resume_checks_slices(tmp_path, monkeypatch):
    import hashlib
    folder=tmp_path/'bil'
    folder.mkdir()
    (folder/'aaaup00ag.hdr').write_text('NROWS 1\nNCOLS 1\nULXMAP 0\nULYMAP 0\n')
    np.array([7],dtype='<f4').tofile(folder/'aaaup00ag.bil')
    monkeypatch.setattr(tables,'COUNT',2)
    tables.ensure_tables(folder,workers=1,maximum=7)
    meta=tables.table_path(folder,7)
    info=json.loads(meta.read_text())
    target=tmp_path/info['file']
    original=target.read_bytes()
    a=np.load(target,mmap_mode='r+')
    states={str(i):hashlib.sha256(a[i*4:(i+1)*4].tobytes()).hexdigest() for i in range(2)}
    a[4]=123  # Corrupt one recorded tile; retain the valid tile.
    a.flush()
    del a
    target.rename(target.with_suffix('.part'))
    target.with_suffix('.state').write_text(json.dumps(dict(fingerprint=info['fingerprint'],tiles=states)))
    meta.unlink()
    submitted=[]
    executor=tables.concurrent.futures.ProcessPoolExecutor
    class RecordingExecutor(executor):
        def submit(self, fn, task):
            submitted.append(task)
            return super().submit(fn,task)
    monkeypatch.setattr(tables.concurrent.futures,'ProcessPoolExecutor',RecordingExecutor)
    tables.ensure_tables(folder,workers=1,maximum=7)
    assert submitted == [(1,(7,))]
    assert target.read_bytes() == original


def test_fingerprint_ignores_configuration_and_docstrings(tmp_path, monkeypatch):
    from mu_calculator import geometry
    folder=tmp_path/'bil'
    folder.mkdir()
    (folder/'aaaup00ag.hdr').write_text('header')
    (folder/'aaaup00ag.bil').write_bytes(b'payload')
    signature=tables.fingerprint(folder)
    monkeypatch.setenv('MU_TABLE_MAX_LEVEL','11')
    monkeypatch.setenv('MU_TABLE_WORKERS','1')
    monkeypatch.setattr(geometry.Grump.pix,'__doc__','Edited documentation')
    assert tables.fingerprint(folder)==signature
    (folder/'aaaup00ag.bil').write_bytes(b'changed payload')
    assert tables.fingerprint(folder)!=signature
