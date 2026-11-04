from pathlib import Path
from types import SimpleNamespace

from utils.kubeflow_utils import read_from_input_artifact, write_to_output_artifact


def test_artifact_directory_round_trip(tmp_path):
    artifact = SimpleNamespace(path=str(tmp_path / "artifacts" / "dataset.tar.gz"))

    with write_to_output_artifact(artifact) as output_dir:
        output_path = Path(output_dir)
        (output_path / "nested").mkdir()
        (output_path / "nested" / "result.json").write_text('{"status": "complete"}')

    assert not output_path.exists()
    assert Path(artifact.path).is_file()

    with read_from_input_artifact(artifact) as input_dir:
        input_path = Path(input_dir)
        assert (input_path / "nested" / "result.json").read_text() == ('{"status": "complete"}')

    assert not input_path.exists()
