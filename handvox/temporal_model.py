"""โมเดลลำดับภาพขนาดเล็กสำหรับ HandVox ที่ใช้ CUDA ได้เมื่อพร้อม.

โมดูลนี้ตั้งใจให้เป็นทางเลือกใหม่โดยไม่ผูกกับหน้าจอหรือขั้นตอนเทรนเดิม:

* รับข้อมูล landmark รูปทรง ``(จำนวนคลิป, จำนวนเฟรม, จำนวนคุณลักษณะ)``
* เลือก CUDA อัตโนมัติ และถอยกลับมาใช้ CPU เมื่อ CUDA ไม่พร้อม
* ใช้ class weight, deterministic seed และ early stopping
* มี ``predict``/``predict_proba`` แบบเดียวกับ estimator ทั่วไป
* บันทึก state dict พร้อมข้อมูลสำคัญที่ใช้ตรวจความเข้ากันได้ของโมเดล

การ import ไฟล์นี้ยังทำได้เมื่อไม่ได้ติดตั้ง PyTorch เพื่อให้ส่วนอื่นของแอป
เปิดใช้งานได้ตามปกติ เมธอดที่ต้องใช้โมเดลจะอธิบาย dependency ที่ขาดแทน
การทำให้โปรแกรมล้มตั้งแต่เริ่มเปิด.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

import numpy as np


try:  # PyTorch เป็น dependency ทางเลือกจนกว่า workflow หลักจะเลือกใช้ TCN
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
    _TORCH_IMPORT_ERROR: Exception | None = None
except (ImportError, OSError) as error:  # รวมกรณี DLL/CUDA runtime โหลดไม่ได้
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment]
    TensorDataset = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False
    _TORCH_IMPORT_ERROR = error


ARTIFACT_FORMAT = "handvox-lightweight-tcn"
ARTIFACT_VERSION = 1


class TorchUnavailableError(RuntimeError):
    """แจ้งว่าฟังก์ชันโมเดล temporal ใช้ไม่ได้เพราะ PyTorch ไม่พร้อม."""


@dataclass(frozen=True)
class DeviceSelection:
    """ผลการเลือกอุปกรณ์ เพื่อให้ GUI แสดงสถานะและเหตุผล fallback ได้."""

    requested: str
    selected: str
    accelerator_available: bool
    fallback_reason: str = ""
    device_name: str = ""


def is_torch_available() -> bool:
    """คืน ``True`` เมื่อ import PyTorch และ runtime ที่จำเป็นสำเร็จ."""

    return TORCH_AVAILABLE


def torch_unavailable_reason() -> str:
    """คืนเหตุผลสั้น ๆ สำหรับแสดงใน GUI เมื่อ PyTorch ใช้งานไม่ได้."""

    if TORCH_AVAILABLE:
        return ""
    if _TORCH_IMPORT_ERROR is None:
        return "ยังไม่ได้ติดตั้ง PyTorch"
    return f"PyTorch ใช้งานไม่ได้: {_TORCH_IMPORT_ERROR}"


def select_device(preferred: str = "auto") -> DeviceSelection:
    """เลือก ``cuda`` เมื่อพร้อม มิฉะนั้น fallback เป็น ``cpu``.

    ``preferred`` รองรับ ``auto``, ``cpu``, ``cuda`` และ ``cuda:N``.
    การขอ CUDA บนเครื่องที่ไม่พร้อมจะไม่ทำให้แอปล้ม แต่คืน CPU พร้อมเหตุผล
    เพื่อให้ผู้ใช้ยังเทรนหรือทดสอบต่อได้.
    """

    requested = str(preferred).strip().lower() or "auto"
    valid = requested in {"auto", "cpu", "cuda"} or requested.startswith("cuda:")
    if not valid:
        raise ValueError("device ต้องเป็น auto, cpu, cuda หรือ cuda:N")
    requested_index = None
    if requested.startswith("cuda:"):
        try:
            requested_index = int(requested.split(":", 1)[1])
        except ValueError as error:
            raise ValueError("device แบบ CUDA ต้องอยู่ในรูป cuda:N") from error
        if requested_index < 0:
            raise ValueError("หมายเลข CUDA device ต้องไม่ติดลบ")
    if not TORCH_AVAILABLE:
        return DeviceSelection(
            requested=requested,
            selected="unavailable",
            accelerator_available=False,
            fallback_reason=torch_unavailable_reason(),
        )

    cuda_ready = bool(torch.cuda.is_available())
    if requested == "cpu":
        return DeviceSelection(requested, "cpu", cuda_ready, device_name="CPU")
    if requested == "auto":
        selected = "cuda" if cuda_ready else "cpu"
        name = torch.cuda.get_device_name(0) if cuda_ready else "CPU"
        return DeviceSelection(requested, selected, cuda_ready, device_name=name)
    if not cuda_ready:
        return DeviceSelection(
            requested,
            "cpu",
            False,
            "CUDA ไม่พร้อม จึงเปลี่ยนไปใช้ CPU อัตโนมัติ",
            "CPU",
        )

    # ตรวจ index ที่ระบุ เพื่อไม่ให้พบ error ล่าช้าตอนย้าย tensor เข้า GPU
    selected = requested
    if requested == "cuda":
        selected = "cuda:0"
    else:
        index = requested_index
        assert index is not None
        if index < 0 or index >= torch.cuda.device_count():
            return DeviceSelection(
                requested,
                "cpu",
                True,
                f"ไม่พบ {requested} จึงเปลี่ยนไปใช้ CPU อัตโนมัติ",
                "CPU",
            )
    cuda_index = torch.device(selected).index
    name = torch.cuda.get_device_name(0 if cuda_index is None else cuda_index)
    return DeviceSelection(requested, selected, True, device_name=name)


def set_deterministic_seed(seed: int) -> None:
    """กำหนด seed ของ Python, NumPy และ PyTorch ให้ทดลองซ้ำได้ใกล้เคียงเดิม."""

    random.seed(seed)
    np.random.seed(seed)
    if not TORCH_AVAILABLE:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    # warn_only ช่วยให้ fallback ได้หาก CUDA operation บางรุ่นไม่มี deterministic kernel
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except (AttributeError, TypeError):
        pass


def _require_torch() -> None:
    if TORCH_AVAILABLE:
        return
    reason = torch_unavailable_reason()
    raise TorchUnavailableError(
        f"โมเดล Temporal ต้องใช้ PyTorch แต่ระบบนี้ยังใช้ไม่ได้ ({reason})"
    )


if TORCH_AVAILABLE:

    class _TemporalResidualBlock(nn.Module):
        """Residual TCN block ที่รักษาความยาวของ sequence ไว้เท่าเดิม."""

        def __init__(
            self,
            input_channels: int,
            output_channels: int,
            kernel_size: int,
            dilation: int,
            dropout: float,
        ):
            super().__init__()
            padding = dilation * (kernel_size - 1) // 2
            self.layers = nn.Sequential(
                nn.Conv1d(
                    input_channels,
                    output_channels,
                    kernel_size,
                    padding=padding,
                    dilation=dilation,
                ),
                nn.GroupNorm(1, output_channels),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Conv1d(
                    output_channels,
                    output_channels,
                    kernel_size,
                    padding=padding,
                    dilation=dilation,
                ),
                nn.GroupNorm(1, output_channels),
                nn.ReLU(),
                nn.Dropout(dropout),
            )
            self.residual = (
                nn.Identity()
                if input_channels == output_channels
                else nn.Conv1d(input_channels, output_channels, kernel_size=1)
            )
            self.output_activation = nn.ReLU()

        def forward(self, values):
            return self.output_activation(self.layers(values) + self.residual(values))


    class LightweightTCN(nn.Module):
        """TCN ขนาดเล็กสำหรับ sequence landmark รูปทรง ``(N, T, F)``."""

        def __init__(
            self,
            input_size: int,
            num_classes: int,
            hidden_channels: Sequence[int] = (64, 64),
            kernel_size: int = 3,
            dropout: float = 0.2,
        ):
            super().__init__()
            channels = tuple(int(value) for value in hidden_channels)
            blocks = []
            current_channels = int(input_size)
            for index, output_channels in enumerate(channels):
                blocks.append(
                    _TemporalResidualBlock(
                        current_channels,
                        output_channels,
                        kernel_size=kernel_size,
                        dilation=2**index,
                        dropout=dropout,
                    )
                )
                current_channels = output_channels
            self.temporal_blocks = nn.Sequential(*blocks)
            # Mean + max pooling จับทั้งภาพรวมและช่วงที่เคลื่อนไหวเด่น โดยไม่เพิ่ม
            # parameter ตามจำนวนเฟรม จึงรองรับ sequence length รุ่นถัดไปได้ง่าย
            self.classifier = nn.Linear(current_channels * 2, int(num_classes))

        def forward(self, sequences):
            features = sequences.transpose(1, 2)  # (N,T,F) -> (N,F,T)
            features = self.temporal_blocks(features)
            pooled = torch.cat(
                (features.mean(dim=-1), features.amax(dim=-1)), dim=1
            )
            return self.classifier(pooled)

else:

    class LightweightTCN:  # pragma: no cover - ข้อความจริงทดสอบผ่าน facade
        """Placeholder ที่ให้ import ได้ แม้เครื่องยังไม่มี PyTorch."""

        def __init__(self, *args, **kwargs):
            _require_torch()


def _python_scalar(value: Any) -> Any:
    """แปลง NumPy scalar เป็นชนิดพื้นฐานที่บันทึกใน artifact ได้อย่างปลอดภัย."""

    return value.item() if isinstance(value, np.generic) else value


def _safe_artifact_value(value: Any) -> Any:
    """จำกัด metadata เป็น primitive/list/dict เพื่อโหลดด้วย weights_only ได้."""

    value = _python_scalar(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return [_safe_artifact_value(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {
            str(key): _safe_artifact_value(item) for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_artifact_value(item) for item in value]
    return str(value)


class TemporalClassifier:
    """Facade สำหรับฝึกและใช้ Lightweight TCN แบบเดียวกับ classifier ทั่วไป.

    พารามิเตอร์ ``input_size`` และ ``sequence_length`` ทำหน้าที่เป็นสัญญา
    ป้องกันการนำโมเดลไปใช้กับ feature schema หรือจำนวนเฟรมผิดรุ่น.
    """

    def __init__(
        self,
        input_size: int,
        sequence_length: int,
        *,
        hidden_channels: Sequence[int] = (64, 64),
        kernel_size: int = 3,
        dropout: float = 0.2,
        learning_rate: float = 1e-3,
        weight_decay: float = 1e-4,
        batch_size: int = 32,
        max_epochs: int = 100,
        patience: int = 10,
        min_delta: float = 1e-4,
        validation_fraction: float = 0.2,
        random_state: int = 42,
        device: str = "auto",
        schema_version: str = "unknown",
    ):
        self.input_size = int(input_size)
        self.sequence_length = int(sequence_length)
        self.hidden_channels = tuple(int(value) for value in hidden_channels)
        self.kernel_size = int(kernel_size)
        self.dropout = float(dropout)
        self.learning_rate = float(learning_rate)
        self.weight_decay = float(weight_decay)
        self.batch_size = int(batch_size)
        self.max_epochs = int(max_epochs)
        self.patience = int(patience)
        self.min_delta = float(min_delta)
        self.validation_fraction = float(validation_fraction)
        self.random_state = int(random_state)
        self.device = str(device)
        self.schema_version = str(schema_version)
        self._validate_hyperparameters()

    def _validate_hyperparameters(self) -> None:
        if self.input_size <= 0 or self.sequence_length <= 0:
            raise ValueError("input_size และ sequence_length ต้องมากกว่า 0")
        if not self.hidden_channels or any(value <= 0 for value in self.hidden_channels):
            raise ValueError("hidden_channels ต้องมีจำนวน channel ที่มากกว่า 0")
        if self.kernel_size <= 0 or self.kernel_size % 2 == 0:
            raise ValueError("kernel_size ต้องเป็นจำนวนคี่ที่มากกว่า 0")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout ต้องอยู่ระหว่าง 0 (รวม) และ 1 (ไม่รวม)")
        if self.learning_rate <= 0 or self.weight_decay < 0:
            raise ValueError("learning_rate ต้องมากกว่า 0 และ weight_decay ต้องไม่ติดลบ")
        if self.batch_size <= 0 or self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("batch_size, max_epochs และ patience ต้องมากกว่า 0")
        if not 0.0 <= self.validation_fraction < 1.0:
            raise ValueError("validation_fraction ต้องอยู่ระหว่าง 0 (รวม) และ 1 (ไม่รวม)")
        # ตรวจรูปแบบ device ตั้งแต่สร้าง object แม้ PyTorch ยังไม่พร้อม
        select_device(self.device)

    def get_params(self) -> dict[str, Any]:
        """คืนพารามิเตอร์ที่จำเป็นสำหรับสร้าง classifier และโหลด artifact."""

        return {
            "input_size": self.input_size,
            "sequence_length": self.sequence_length,
            "hidden_channels": self.hidden_channels,
            "kernel_size": self.kernel_size,
            "dropout": self.dropout,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "batch_size": self.batch_size,
            "max_epochs": self.max_epochs,
            "patience": self.patience,
            "min_delta": self.min_delta,
            "validation_fraction": self.validation_fraction,
            "random_state": self.random_state,
            "device": self.device,
            "schema_version": self.schema_version,
        }

    def _validate_sequences(self, values, *, allow_single: bool = False) -> np.ndarray:
        sequences = np.asarray(values, dtype=np.float32)
        if allow_single and sequences.ndim == 2:
            sequences = sequences[np.newaxis, ...]
        expected = (self.sequence_length, self.input_size)
        if sequences.ndim != 3 or tuple(sequences.shape[1:]) != expected:
            raise ValueError(
                "ข้อมูลต้องมี shape "
                f"(จำนวนคลิป, {self.sequence_length}, {self.input_size})"
            )
        if len(sequences) == 0:
            raise ValueError("ต้องมี sequence อย่างน้อย 1 รายการ")
        if not np.isfinite(sequences).all():
            raise ValueError("ข้อมูล sequence มี NaN หรือ Infinity")
        return np.ascontiguousarray(sequences, dtype=np.float32)

    @staticmethod
    def _validate_labels(values, expected_length: int, name: str = "y") -> np.ndarray:
        labels = np.asarray(values)
        if labels.ndim != 1 or len(labels) != expected_length:
            raise ValueError(f"{name} ต้องเป็นเวกเตอร์ที่มี {expected_length} ค่า")
        return labels

    def _internal_validation_split(self, sequences, encoded_labels):
        """กัน validation รายคลาสแบบ deterministic โดยไม่ทำคลาสหายจาก train."""

        if self.validation_fraction <= 0:
            return sequences, encoded_labels, None, None
        rng = np.random.default_rng(self.random_state)
        train_indices: list[int] = []
        validation_indices: list[int] = []
        for class_index in np.unique(encoded_labels):
            indices = np.flatnonzero(encoded_labels == class_index)
            rng.shuffle(indices)
            if len(indices) < 2:
                validation_count = 0
            else:
                validation_count = max(
                    1, int(round(len(indices) * self.validation_fraction))
                )
                validation_count = min(validation_count, len(indices) - 1)
            validation_indices.extend(indices[:validation_count].tolist())
            train_indices.extend(indices[validation_count:].tolist())
        if not validation_indices:
            return sequences, encoded_labels, None, None
        train_indices.sort()
        validation_indices.sort()
        return (
            sequences[train_indices],
            encoded_labels[train_indices],
            sequences[validation_indices],
            encoded_labels[validation_indices],
        )

    @staticmethod
    def _balanced_class_weights(encoded_labels: np.ndarray, class_count: int):
        counts = np.bincount(encoded_labels, minlength=class_count).astype(np.float32)
        if np.any(counts == 0):
            raise ValueError("ชุด train ต้องมีตัวอย่างของทุกคลาส")
        weights = len(encoded_labels) / (class_count * counts)
        return weights.astype(np.float32)

    def _build_model(self, class_count: int):
        return LightweightTCN(
            input_size=self.input_size,
            num_classes=class_count,
            hidden_channels=self.hidden_channels,
            kernel_size=self.kernel_size,
            dropout=self.dropout,
        )

    def fit(self, X, y, *, X_val=None, y_val=None):
        """ฝึกโมเดล และหยุดเมื่อ validation loss ไม่ดีขึ้นตาม ``patience``.

        หากไม่ส่ง validation set จะกันข้อมูลรายคลาสตาม
        ``validation_fraction``. ใน workflow จริงควรส่ง validation ที่แบ่งตาม
        signer/session มาให้โดยตรงเพื่อป้องกันข้อมูลรั่ว.
        """

        _require_torch()
        set_deterministic_seed(self.random_state)
        sequences = self._validate_sequences(X)
        labels = self._validate_labels(y, len(sequences))
        self.classes_ = np.unique(labels)
        if len(self.classes_) < 2:
            raise ValueError("TemporalClassifier ต้องมีอย่างน้อย 2 คลาส")
        label_to_index = {
            _python_scalar(label): index for index, label in enumerate(self.classes_)
        }
        encoded_labels = np.asarray(
            [label_to_index[_python_scalar(label)] for label in labels],
            dtype=np.int64,
        )

        if (X_val is None) != (y_val is None):
            raise ValueError("ต้องส่ง X_val และ y_val มาด้วยกัน")
        if X_val is None:
            train_x, train_y, validation_x, validation_y = (
                self._internal_validation_split(sequences, encoded_labels)
            )
        else:
            train_x, train_y = sequences, encoded_labels
            validation_x = self._validate_sequences(X_val)
            validation_labels = self._validate_labels(
                y_val, len(validation_x), name="y_val"
            )
            unknown = sorted(
                {
                    str(_python_scalar(label))
                    for label in validation_labels
                    if _python_scalar(label) not in label_to_index
                }
            )
            if unknown:
                raise ValueError("validation มีคลาสที่ไม่อยู่ใน train: " + ", ".join(unknown))
            validation_y = np.asarray(
                [label_to_index[_python_scalar(label)] for label in validation_labels],
                dtype=np.int64,
            )

        self.device_selection_ = select_device(self.device)
        if self.device_selection_.selected == "unavailable":
            _require_torch()
        self.device_used_ = self.device_selection_.selected
        torch_device = torch.device(self.device_used_)
        self.model_ = self._build_model(len(self.classes_))
        try:
            self.model_ = self.model_.to(torch_device)
        except RuntimeError as error:
            if not self.device_used_.startswith("cuda"):
                raise
            # CUDA อาจถูกตรวจพบแต่เริ่ม context ไม่สำเร็จ/หน่วยความจำไม่พอ
            # จึงรักษาความสามารถใช้งานของแอปด้วย CPU พร้อมบันทึกเหตุผลไว้
            self.device_selection_ = DeviceSelection(
                requested=self.device_selection_.requested,
                selected="cpu",
                accelerator_available=True,
                fallback_reason=f"เริ่มใช้ CUDA ไม่สำเร็จ จึงใช้ CPU: {error}",
                device_name="CPU",
            )
            self.device_used_ = "cpu"
            torch_device = torch.device("cpu")
            self.model_ = self.model_.to(torch_device)

        class_weights = self._balanced_class_weights(train_y, len(self.classes_))
        self.class_weights_ = class_weights.copy()
        loss_function = nn.CrossEntropyLoss(
            weight=torch.as_tensor(class_weights, dtype=torch.float32, device=torch_device)
        )
        optimizer = torch.optim.AdamW(
            self.model_.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        generator = torch.Generator()
        generator.manual_seed(self.random_state)
        train_dataset = TensorDataset(
            torch.from_numpy(train_x), torch.from_numpy(train_y)
        )
        train_loader = DataLoader(
            train_dataset,
            batch_size=min(self.batch_size, len(train_dataset)),
            shuffle=True,
            num_workers=0,
            generator=generator,
            pin_memory=self.device_used_.startswith("cuda"),
        )

        validation_tensors = None
        if validation_x is not None:
            validation_tensors = (
                torch.from_numpy(validation_x),
                torch.from_numpy(validation_y),
            )

        self.history_ = []
        best_loss = float("inf")
        best_epoch = 0
        best_state = None
        stale_epochs = 0
        for epoch in range(1, self.max_epochs + 1):
            self.model_.train()
            total_loss = 0.0
            total_samples = 0
            for batch_x, batch_y in train_loader:
                batch_x = batch_x.to(torch_device, non_blocking=True)
                batch_y = batch_y.to(torch_device, non_blocking=True)
                optimizer.zero_grad(set_to_none=True)
                logits = self.model_(batch_x)
                loss = loss_function(logits, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.detach().cpu()) * len(batch_x)
                total_samples += len(batch_x)
            train_loss = total_loss / max(total_samples, 1)

            validation_loss = train_loss
            if validation_tensors is not None:
                self.model_.eval()
                with torch.no_grad():
                    val_x_tensor, val_y_tensor = validation_tensors
                    logits = self.model_(val_x_tensor.to(torch_device))
                    validation_loss = float(
                        loss_function(logits, val_y_tensor.to(torch_device)).cpu()
                    )
            self.history_.append(
                {
                    "epoch": epoch,
                    "train_loss": train_loss,
                    "validation_loss": validation_loss,
                }
            )

            if validation_loss < best_loss - self.min_delta:
                best_loss = validation_loss
                best_epoch = epoch
                best_state = {
                    name: value.detach().cpu().clone()
                    for name, value in self.model_.state_dict().items()
                }
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= self.patience:
                    break

        if best_state is None:  # ป้องกันกรณี loss ผิดปกติ แม้ข้อมูลผ่าน finite check
            raise RuntimeError("เทรนโมเดลไม่สำเร็จ: ไม่พบ epoch ที่มี loss ใช้งานได้")
        self.model_.load_state_dict(best_state)
        self.model_.eval()
        self.n_epochs_ = len(self.history_)
        self.best_epoch_ = best_epoch
        self.best_validation_loss_ = best_loss
        self.stopped_early_ = self.n_epochs_ < self.max_epochs
        self.training_samples_ = len(train_x)
        self.validation_samples_ = 0 if validation_x is None else len(validation_x)
        self.fitted_at_utc_ = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.is_fitted_ = True
        return self

    def _check_fitted(self) -> None:
        if not getattr(self, "is_fitted_", False) or not hasattr(self, "model_"):
            raise RuntimeError("TemporalClassifier ยังไม่ได้ fit หรือ load โมเดล")

    def predict_proba(self, X) -> np.ndarray:
        """คืน probability รูปทรง ``(N, จำนวนคลาส)`` ตามลำดับ ``classes_``."""

        _require_torch()
        self._check_fitted()
        sequences = self._validate_sequences(X, allow_single=True)
        torch_device = torch.device(self.device_used_)
        probabilities = []
        self.model_.eval()
        with torch.no_grad():
            for start in range(0, len(sequences), self.batch_size):
                batch = torch.from_numpy(
                    sequences[start : start + self.batch_size]
                ).to(torch_device)
                probabilities.append(
                    torch.softmax(self.model_(batch), dim=1).cpu().numpy()
                )
        return np.concatenate(probabilities, axis=0).astype(np.float32, copy=False)

    def predict(self, X) -> np.ndarray:
        """คืนชื่อคลาสที่มี probability สูงสุดสำหรับแต่ละ sequence."""

        indices = np.argmax(self.predict_proba(X), axis=1)
        return self.classes_[indices]

    def artifact_metadata(self) -> dict[str, Any]:
        """คืน metadata หลักที่ workflow ใช้ตรวจและสร้างรายงานได้."""

        self._check_fitted()
        return {
            "artifact_format": ARTIFACT_FORMAT,
            "artifact_version": ARTIFACT_VERSION,
            "classes": [_python_scalar(value) for value in self.classes_],
            "input_size": self.input_size,
            "sequence_length": self.sequence_length,
            "device_used": self.device_used_,
            "device_requested": self.device,
            "device_fallback_reason": self.device_selection_.fallback_reason,
            "device_name": self.device_selection_.device_name,
            "schema_version": self.schema_version,
            "trained_at_utc": self.fitted_at_utc_,
            "training_samples": self.training_samples_,
            "validation_samples": self.validation_samples_,
            "epochs_completed": self.n_epochs_,
            "best_epoch": self.best_epoch_,
            "best_validation_loss": self.best_validation_loss_,
            "stopped_early": self.stopped_early_,
        }

    def save(self, path, *, metadata: Mapping[str, Any] | None = None) -> Path:
        """บันทึก state dict และ metadata โดยไม่ pickle ตัว classifier ทั้งก้อน."""

        _require_torch()
        self._check_fitted()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        artifact_metadata = self.artifact_metadata()
        if metadata:
            artifact_metadata["custom"] = _safe_artifact_value(dict(metadata))
        payload = {
            "artifact_format": ARTIFACT_FORMAT,
            "artifact_version": ARTIFACT_VERSION,
            "config": self.get_params(),
            "classes": [_python_scalar(value) for value in self.classes_],
            "state_dict": {
                name: value.detach().cpu()
                for name, value in self.model_.state_dict().items()
            },
            "metadata": artifact_metadata,
            "history": list(self.history_),
            "class_weights": self.class_weights_.tolist(),
        }
        torch.save(payload, target)
        self.artifact_metadata_ = artifact_metadata
        return target

    @classmethod
    def load(cls, path, *, device: str = "auto") -> "TemporalClassifier":
        """โหลด artifact แล้ว map โมเดลไป CUDA/CPU ที่พร้อมบนเครื่องปัจจุบัน."""

        _require_torch()
        selection = select_device(device)
        if selection.selected == "unavailable":
            _require_torch()
        target = Path(path)
        try:
            payload = torch.load(
                target, map_location="cpu", weights_only=True
            )
        except TypeError:  # รองรับ PyTorch รุ่นก่อนมีพารามิเตอร์ weights_only
            payload = torch.load(target, map_location="cpu")
        if not isinstance(payload, dict):
            raise ValueError("ไฟล์ temporal model ไม่ใช่ artifact ที่รองรับ")
        if payload.get("artifact_format") != ARTIFACT_FORMAT:
            raise ValueError("รูปแบบ temporal model ไม่ตรงกับ HandVox")
        if payload.get("artifact_version") != ARTIFACT_VERSION:
            raise ValueError("รุ่น artifact ของ temporal model ยังไม่รองรับ")

        config = dict(payload.get("config", {}))
        config["device"] = device
        estimator = cls(**config)
        estimator.classes_ = np.asarray(payload["classes"])
        if len(estimator.classes_) < 2:
            raise ValueError("artifact ต้องมีอย่างน้อย 2 คลาส")
        estimator.device_selection_ = selection
        estimator.device_used_ = selection.selected
        estimator.model_ = estimator._build_model(len(estimator.classes_))
        try:
            estimator.model_ = estimator.model_.to(torch.device(selection.selected))
        except RuntimeError as error:
            if not selection.selected.startswith("cuda"):
                raise
            selection = DeviceSelection(
                requested=selection.requested,
                selected="cpu",
                accelerator_available=True,
                fallback_reason=f"โหลดโมเดลเข้า CUDA ไม่สำเร็จ จึงใช้ CPU: {error}",
                device_name="CPU",
            )
            estimator.device_selection_ = selection
            estimator.device_used_ = "cpu"
            estimator.model_ = estimator.model_.to(torch.device("cpu"))
        estimator.model_.load_state_dict(payload["state_dict"])
        estimator.model_.eval()

        artifact_metadata = dict(payload.get("metadata", {}))
        estimator.artifact_metadata_ = artifact_metadata
        estimator.history_ = list(payload.get("history", []))
        estimator.class_weights_ = np.asarray(
            payload.get("class_weights", [1.0] * len(estimator.classes_)),
            dtype=np.float32,
        )
        estimator.n_epochs_ = int(
            artifact_metadata.get("epochs_completed", len(estimator.history_))
        )
        estimator.best_epoch_ = int(artifact_metadata.get("best_epoch", 0))
        estimator.best_validation_loss_ = float(
            artifact_metadata.get("best_validation_loss", float("nan"))
        )
        estimator.stopped_early_ = bool(
            artifact_metadata.get("stopped_early", False)
        )
        estimator.training_samples_ = int(
            artifact_metadata.get("training_samples", 0)
        )
        estimator.validation_samples_ = int(
            artifact_metadata.get("validation_samples", 0)
        )
        estimator.fitted_at_utc_ = str(artifact_metadata.get("trained_at_utc", ""))
        estimator.trained_device_ = str(
            artifact_metadata.get("device_used", "unknown")
        )
        estimator.is_fitted_ = True
        return estimator


__all__ = [
    "ARTIFACT_FORMAT",
    "ARTIFACT_VERSION",
    "TORCH_AVAILABLE",
    "DeviceSelection",
    "LightweightTCN",
    "TemporalClassifier",
    "TorchUnavailableError",
    "is_torch_available",
    "select_device",
    "set_deterministic_seed",
    "torch_unavailable_reason",
]
