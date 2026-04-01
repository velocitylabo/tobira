"""Tests for tobira.core.gguf_export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestExportGguf:
    def test_missing_model_dir_raises(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import export_gguf

        with pytest.raises(FileNotFoundError, match="Model directory not found"):
            export_gguf(tmp_path / "nonexistent")

    def test_missing_config_json_raises(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import export_gguf

        model_dir = tmp_path / "model"
        model_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="No config.json found"):
            export_gguf(model_dir)

    def test_unsupported_quant_type_raises(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import export_gguf

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        with pytest.raises(ValueError, match="Unsupported quant_type"):
            export_gguf(model_dir, quant_type="invalid")

    @patch("tobira.core.gguf_export._find_convert_command")
    @patch("tobira.core.gguf_export.subprocess")
    def test_export_calls_convert(
        self,
        mock_subprocess: MagicMock,
        mock_find_cmd: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tobira.core.gguf_export import export_gguf

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        mock_find_cmd.return_value = ["convert-hf-to-gguf"]

        output_path = model_dir / "model-q8_0.gguf"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result

        # Create the output file to simulate conversion
        output_path.touch()

        result = export_gguf(model_dir)
        assert result == output_path

        mock_subprocess.run.assert_called_once()
        call_args = mock_subprocess.run.call_args
        cmd = call_args[0][0]
        assert "convert-hf-to-gguf" in cmd
        assert "--outtype" in cmd
        assert "q8_0" in cmd

    @patch("tobira.core.gguf_export._find_convert_command")
    @patch("tobira.core.gguf_export.subprocess")
    def test_export_custom_output_and_quant(
        self,
        mock_subprocess: MagicMock,
        mock_find_cmd: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tobira.core.gguf_export import export_gguf

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        mock_find_cmd.return_value = ["convert-hf-to-gguf"]

        custom_output = tmp_path / "custom" / "out.gguf"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result

        custom_output.parent.mkdir(parents=True)
        custom_output.touch()

        result = export_gguf(model_dir, output_path=custom_output, quant_type="f16")
        assert result == custom_output

    @patch("tobira.core.gguf_export._find_convert_command")
    @patch("tobira.core.gguf_export.subprocess")
    def test_export_conversion_failure_raises(
        self,
        mock_subprocess: MagicMock,
        mock_find_cmd: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tobira.core.gguf_export import export_gguf

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        mock_find_cmd.return_value = ["convert-hf-to-gguf"]

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "conversion error"
        mock_subprocess.run.return_value = mock_result

        with pytest.raises(RuntimeError, match="GGUF conversion failed"):
            export_gguf(model_dir)


class TestGenerateModelfile:
    def test_generates_modelfile(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import generate_modelfile

        gguf_path = tmp_path / "model.gguf"
        gguf_path.touch()

        result = generate_modelfile(gguf_path)

        assert result == tmp_path / "Modelfile"
        assert result.exists()

        content = result.read_text()
        assert f"FROM {gguf_path.resolve()}" in content
        assert "SYSTEM" in content
        assert "spam classifier" in content
        assert "PARAMETER temperature" in content

    def test_custom_system_prompt(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import generate_modelfile

        gguf_path = tmp_path / "model.gguf"
        gguf_path.touch()

        custom_prompt = "Custom spam detection prompt."
        result = generate_modelfile(gguf_path, system_prompt=custom_prompt)

        content = result.read_text()
        assert custom_prompt in content

    def test_custom_output_path(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import generate_modelfile

        gguf_path = tmp_path / "model.gguf"
        gguf_path.touch()

        custom_output = tmp_path / "custom" / "MyModelfile"
        result = generate_modelfile(gguf_path, output_path=custom_output)

        assert result == custom_output
        assert result.exists()

    def test_model_name_in_comment(self, tmp_path: Path) -> None:
        from tobira.core.gguf_export import generate_modelfile

        gguf_path = tmp_path / "model.gguf"
        gguf_path.touch()

        result = generate_modelfile(gguf_path, model_name="my-model")
        content = result.read_text()
        assert "my-model" in content


class TestFindConvertCommand:
    @patch("tobira.core.gguf_export.shutil.which")
    def test_finds_on_path(self, mock_which: MagicMock) -> None:
        from tobira.core.gguf_export import _find_convert_command

        mock_which.return_value = "/usr/bin/convert-hf-to-gguf"
        result = _find_convert_command()
        assert result == ["/usr/bin/convert-hf-to-gguf"]

    @patch("tobira.core.gguf_export.shutil.which")
    def test_fallback_to_module(self, mock_which: MagicMock) -> None:
        import sys

        from tobira.core.gguf_export import _find_convert_command

        mock_which.return_value = None
        with patch.dict("sys.modules", {"gguf": MagicMock()}):
            result = _find_convert_command()
            assert result == [sys.executable, "-m", "gguf.convert_hf_to_gguf"]

    @patch("tobira.core.gguf_export.shutil.which")
    def test_missing_gguf_raises(self, mock_which: MagicMock) -> None:
        from tobira.core.gguf_export import _find_convert_command

        mock_which.return_value = None
        with patch.dict("sys.modules", {"gguf": None}):
            with pytest.raises(ImportError, match="gguf"):
                _find_convert_command()


class TestSupportedQuantTypes:
    def test_common_types_present(self) -> None:
        from tobira.core.gguf_export import SUPPORTED_QUANT_TYPES

        for t in ("f32", "f16", "q8_0", "q4_0"):
            assert t in SUPPORTED_QUANT_TYPES


class TestCorePublicAPI:
    def test_imports_gguf_export(self) -> None:
        from tobira.core import export_gguf, generate_modelfile

        assert export_gguf is not None
        assert generate_modelfile is not None

    def test_imports_causal_trainer(self) -> None:
        from tobira.core import (
            CausalTrainingConfig,
            CausalTrainingResult,
            train_causal,
        )

        assert CausalTrainingConfig is not None
        assert CausalTrainingResult is not None
        assert train_causal is not None
