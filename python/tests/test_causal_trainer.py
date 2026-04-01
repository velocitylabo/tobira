"""Tests for tobira.core.causal_trainer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCausalTrainingConfig:
    def test_defaults(self) -> None:
        from tobira.core.causal_trainer import CausalTrainingConfig

        config = CausalTrainingConfig()
        assert config.model_name == "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
        assert config.epochs == 3
        assert config.batch_size == 4
        assert config.learning_rate == 2e-4
        assert config.lora_r == 16
        assert config.lora_alpha == 32
        assert config.label_names == ["ham", "spam"]


class TestCausalTrainingResult:
    def test_fields(self) -> None:
        from tobira.core.causal_trainer import CausalTrainingResult

        result = CausalTrainingResult(
            model_name="test",
            output_path="/tmp/out",
            num_samples=100,
            epochs=3,
            final_loss=0.5,
        )
        assert result.model_name == "test"
        assert result.gguf_path is None


class TestFormatExample:
    def test_format_contains_label(self) -> None:
        from tobira.core.causal_trainer import _format_example

        text = _format_example("Win a prize!", "spam")
        assert '"label": "spam"' in text
        assert "Win a prize!" in text
        # Fallback template used when no tokenizer provided
        assert "<|system|>" in text
        assert "<|user|>" in text
        assert "<|assistant|>" in text
        assert "spam classifier" in text

    def test_format_ham(self) -> None:
        from tobira.core.causal_trainer import _format_example

        text = _format_example("Meeting tomorrow", "ham")
        assert '"label": "ham"' in text

    def test_response_has_no_hardcoded_score(self) -> None:
        from tobira.core.causal_trainer import _format_example

        text = _format_example("Test email", "spam")
        # The assistant response should be just {"label": "spam"} without score
        # (the system prompt may mention "score" in its instructions, that's OK)
        assert '{"label": "spam"}' in text

    def test_format_with_tokenizer_chat_template(self) -> None:
        from tobira.core.causal_trainer import _format_example

        mock_tokenizer = MagicMock()
        mock_tokenizer.apply_chat_template.return_value = (
            "[INST] Classify this email:\n\nHello [/INST] {\"label\": \"ham\"}"
        )

        text = _format_example("Hello", "ham", tokenizer=mock_tokenizer)
        mock_tokenizer.apply_chat_template.assert_called_once()
        assert "Hello" in text
        assert '"label": "ham"' in text
        # Should NOT use fallback template tokens
        assert "<|system|>" not in text


class TestTrainCausal:
    def test_empty_data_raises(self) -> None:
        from tobira.core.causal_trainer import train_causal

        with pytest.raises(ValueError, match="data must not be empty"):
            train_causal([], "/tmp/out")

    def test_unknown_labels_raises(self) -> None:
        from tobira.core.causal_trainer import CausalTrainingConfig, train_causal

        data = [{"text": "hello", "label": "unknown"}]
        config = CausalTrainingConfig()

        with pytest.raises(ValueError, match="unknown labels"):
            train_causal(data, "/tmp/out", config)

    @patch("tobira.core.causal_trainer._import_deps")
    def test_train_flow(self, mock_import: MagicMock, tmp_path: MagicMock) -> None:
        from tobira.core.causal_trainer import CausalTrainingConfig, train_causal

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.device.return_value = MagicMock()
        mock_torch.float32 = "float32"
        mock_torch.float16 = "float16"

        # Mock tensor operations
        mock_tensor = MagicMock()
        mock_torch.tensor.return_value = mock_tensor
        mock_torch.randperm.return_value = list(range(4))
        mock_torch.manual_seed.return_value = None

        # Mock model
        mock_model_class = MagicMock()
        mock_model = MagicMock()
        mock_model_class.from_pretrained.return_value = mock_model

        # Mock tokenizer
        mock_tokenizer_class = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.pad_token = None
        mock_tokenizer.eos_token = "<eos>"
        mock_tokenizer.return_value = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        # Mock peft
        mock_lora_config = MagicMock()
        mock_get_peft = MagicMock()
        mock_peft_model = MagicMock()
        mock_get_peft.return_value = mock_peft_model

        # Make parameters iterable
        mock_param = MagicMock()
        mock_param.requires_grad = True
        mock_param.numel.return_value = 1000
        mock_peft_model.parameters.return_value = [mock_param]
        mock_peft_model.named_modules.return_value = [("q_proj", MagicMock())]

        # Mock training output
        mock_output = MagicMock()
        mock_output.loss = MagicMock()
        mock_output.loss.__float__ = lambda self: 0.5
        mock_peft_model.return_value = mock_output

        # Mock merge_and_unload
        mock_merged = MagicMock()
        mock_peft_model.merge_and_unload.return_value = mock_merged

        mock_import.return_value = (
            mock_torch,
            mock_model_class,
            mock_tokenizer_class,
            mock_lora_config,
            mock_get_peft,
        )

        data = [
            {"text": "Win money!", "label": "spam"},
            {"text": "Meeting at 3pm", "label": "ham"},
            {"text": "Free pills", "label": "spam"},
            {"text": "Project update", "label": "ham"},
        ]

        config = CausalTrainingConfig(
            epochs=1, eval_split=0.0, lora_target_modules=["q_proj", "v_proj"]
        )
        result = train_causal(data, str(tmp_path), config)

        assert result.num_samples == 4
        assert result.epochs == 1
        mock_merged.save_pretrained.assert_called_once()
        mock_tokenizer.save_pretrained.assert_called_once()


class TestDetectTargetModules:
    def test_detects_qv_proj(self) -> None:
        from tobira.core.causal_trainer import _detect_target_modules

        mock_model = MagicMock()
        mock_model.named_modules.return_value = [
            ("model.layers.0.self_attn.q_proj", MagicMock()),
            ("model.layers.0.self_attn.v_proj", MagicMock()),
            ("model.layers.0.mlp.gate_proj", MagicMock()),
        ]

        modules = _detect_target_modules(mock_model)
        assert "q_proj" in modules
        assert "v_proj" in modules

    def test_fallback_to_linear_layer_names(self) -> None:
        from tobira.core.causal_trainer import _detect_target_modules

        try:
            import torch.nn as nn
        except ImportError:
            pytest.skip("torch not installed")

        mock_model = MagicMock()
        linear_mod = nn.Linear(10, 10)
        mock_model.named_modules.return_value = [
            ("layers.0.dense", linear_mod),
            ("layers.1.dense", linear_mod),
        ]

        modules = _detect_target_modules(mock_model)
        assert "layers.0.dense" in modules
        assert "layers.1.dense" in modules


class TestImportError:
    @patch.dict("sys.modules", {"torch": None})
    def test_missing_torch_raises(self) -> None:
        from tobira.core.causal_trainer import _import_deps

        with pytest.raises(ImportError, match="torch and transformers"):
            _import_deps()
