import numpy as np

from backend.src.prediction.fi2010_benchmark import load_fi2010_file


def test_load_fi2010_file_transposes_rows_and_normalizes_labels(tmp_path):
    raw = np.zeros((149, 3), dtype=float)
    raw[:144] = np.arange(144, dtype=float)[:, None]
    raw[144] = [1, 2, 3]
    raw[145:] = 2
    path = tmp_path / "fold.txt"
    np.savetxt(path, raw)

    features, labels = load_fi2010_file(path, horizon_events=10)

    assert features.shape == (3, 144)
    assert features[0, 0] == 0
    assert features[0, -1] == 143
    assert labels.tolist() == [0, 1, 2]
