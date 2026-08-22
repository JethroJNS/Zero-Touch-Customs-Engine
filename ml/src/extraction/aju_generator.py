from __future__ import annotations

import json
import logging
import threading
import re
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any

logger = logging.getLogger("aju_generator")

# Full 26-digit AJU
AJU_PATTERN = re.compile(r"^\d{4}\d{2}\d{6}\d{8}\d{6}$")
# Validasi struktur AJU
AJU_STRUCTURE = re.compile(
    r"^(?P<kode_kantor>\d{4})"
    r"(?P<kode_dok>\d{2})"
    r"(?P<niper>\d{6})"
    r"(?P<tanggal>\d{8})"
    r"(?P<sequence>\d{6})$"
)

# Kode Dokumen mapping
KODE_DOKUMEN: Dict[str, str] = {
    "pib": "01",   # Pemberitahuan Impor Barang
    "peb": "23",   # Pemberitahuan Ekspor Barang
    "bc11": "11",  # BC 1.1
    "bc12": "12",  # BC 1.2
    "bc15": "15",  # BC 1.5
    "bc23": "23",  # BC 2.3
    "bc25": "25",  # BC 2.5
    "bc27": "27",  # BC 2.7
    "01": "01",
    "23": "23",
    "11": "11",
    "12": "12",
    "15": "15",
    "25": "25",
    "27": "27",
}

# Chapter HS valid
VALID_HS_CHAPTERS = set(range(1, 98))


class AJUValidationError(ValueError):
    pass


class AJUGenerator:
    LOCK = threading.Lock()

    def __init__(
        self,
        config_path: Optional[str | Path] = None,
        kode_kantor: Optional[str] = None,
        niper: Optional[str] = None,
        kode_dok_default: str = "01",
    ):
        self._config: Dict[str, Any] = {}
        self._sequence_file: Optional[Path] = None
        self._sequence: int = 1
        self._kode_kantor: str = ""
        self._niper: str = ""
        self._kode_dok_default: str = kode_dok_default
        self._initialized: bool = False

        if config_path:
            self._load_config(Path(config_path))
        elif kode_kantor and niper:
            self._kode_kantor = self._validate_kode_kantor(kode_kantor)
            self._niper = self._validate_niper(niper)
            self._initialized = True

    def _load_config(self, config_path: Path) -> None:
        try:
            with open(config_path) as f:
                self._config = json.load(f)

            ceisa = self._config.get("ceisa", {})
            self._kode_kantor = self._validate_kode_kantor(
                ceisa.get("kode_kantor", "")
            )
            self._niper = self._validate_niper(
                ceisa.get("niper", "")
            )
            aju_cfg = self._config.get("aju_generator", {})
            self._kode_dok_default = "01"

            seq_file = aju_cfg.get("auto_increment_file")
            if seq_file:
                self._sequence_file = (config_path.parent / seq_file).resolve()

            self._load_sequence()
            self._initialized = True
            logger.info(
                f"AJU Generator initialized: "
                f"kode_kantor={self._kode_kantor}, niper=***, "
                f"sequence={self._sequence}"
            )

        except FileNotFoundError:
            raise AJUValidationError(
                f"Config file not found: {config_path}. "
                f"Please create ml/company_config.json with kode_kantor and niper."
            )
        except json.JSONDecodeError as e:
            raise AJUValidationError(f"Invalid JSON in config: {e}")

    def _load_sequence(self) -> None:
        if not self._sequence_file:
            return
        try:
            if self._sequence_file.exists():
                with open(self._sequence_file) as f:
                    content = f.read().strip()
                parts = content.split(",")
                if len(parts) == 2:
                    file_date = parts[0]
                    self._sequence = int(parts[1])
                    today = datetime.now().strftime("%Y%m%d")
                    if file_date != today:
                        self._sequence = 1
                        logger.info(f"[AJU] New day detected ({today}), resetting sequence to 1")
                else:
                    self._sequence = 1
            else:
                self._sequence = 1
        except (ValueError, IOError):
            self._sequence = 1

    def _save_sequence(self) -> None:
        if not self._sequence_file:
            return
        try:
            self._sequence_file.parent.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y%m%d")
            with open(self._sequence_file, "w") as f:
                f.write(f"{today},{self._sequence}\n")
        except IOError as e:
            logger.warning(f"[AJU] Could not save sequence file: {e}")

    @staticmethod
    def _validate_kode_kantor(value: str) -> str:
        if not value or value == "***":
            raise AJUValidationError(
                "kode_kantor not configured. "
                "Set ceisa.kode_kantor in ml/company_config.json"
            )
        if not re.match(r"^\d{4}$", value):
            raise AJUValidationError(
                f"kode_kantor must be 4 digits, got: {value!r}"
            )
        return value

    @staticmethod
    def _validate_niper(value: str) -> str:
        if not value or value == "***":
            raise AJUValidationError(
                "niper not configured. "
                "Set ceisa.niper in ml/company_config.json"
            )
        if not re.match(r"^\d{6}$", value):
            raise AJUValidationError(
                f"niper must be 6 digits, got: {value!r}"
            )
        return value

    @staticmethod
    def _validate_kode_dok(value: str) -> str:
        if value not in KODE_DOKUMEN:
            raise AJUValidationError(
                f"Invalid kode_dok: {value!r}. "
                f"Valid values: {list(KODE_DOKUMEN.keys())}"
            )
        return KODE_DOKUMEN[value]

    @staticmethod
    def _validate_date(value: str | date) -> str:
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d", "%d.%m.%Y"):
            try:
                dt = datetime.strptime(str(value).strip(), fmt)
                return dt.strftime("%Y%m%d")
            except ValueError:
                continue
        raise AJUValidationError(
            f"Invalid date format: {value!r}. "
            f"Use YYYY-MM-DD, DD/MM/YYYY, or YYYYMMDD."
        )

    @staticmethod
    def _validate_sequence(value: int) -> str:
        if not 1 <= value <= 999999:
            raise AJUValidationError(
                f"sequence must be 1-999999, got: {value}"
            )
        return f"{value:06d}"

    def generate_aju(
        self,
        document_type: str = "pib",
        shipment_date: Optional[str | date] = None,
        kode_kantor: Optional[str] = None,
        kode_dok: Optional[str] = None,
        niper: Optional[str] = None,
    ) -> str:
        if not self._initialized:
            raise AJUValidationError(
                "AJU Generator not initialized. "
                "Pass config_path or kode_kantor+niper to constructor."
            )

        kk = kode_kantor or self._kode_kantor
        np_ = niper or self._niper
        kd = kode_dok or KODE_DOKUMEN.get(document_type, self._kode_dok_default)
        kd = self._validate_kode_dok(kd) if isinstance(kd, str) else kd
        if not re.match(r"^\d{2}$", str(kd)):
            kd = self._validate_kode_dok(document_type)

        dt = shipment_date or datetime.now().date()
        tanggal = self._validate_date(dt)

        # Thread-safe sequence increment
        with self.LOCK:
            seq_str = self._validate_sequence(self._sequence)
            self._sequence += 1
            self._save_sequence()

        aju = f"{kk}{kd}{np_}{tanggal}{seq_str}"

        if not AJU_PATTERN.match(aju):
            raise AJUValidationError(
                f"Generated AJU failed validation: {aju!r} "
                f"(length={len(aju)}, expected 26)"
            )

        logger.info(f"[AJU] Generated: {aju} (doc={document_type}, date={tanggal})")
        return aju

    def generate_batch(
        self,
        count: int,
        document_type: str = "pib",
        shipment_date: Optional[str | date] = None,
        **kwargs,
    ) -> list[str]:
        if not 1 <= count <= 100:
            raise AJUValidationError(f"count must be 1-100, got: {count}")

        results = []
        for _ in range(count):
            results.append(self.generate_aju(
                document_type=document_type,
                shipment_date=shipment_date,
                **kwargs,
            ))
        return results

    @staticmethod
    def validate(aju: str) -> Dict[str, Any]:
        result = {
            "aju": aju,
            "kode_kantor": None,
            "kode_dok": None,
            "kode_dok_name": None,
            "niper": None,
            "tanggal": None,
            "tanggal_readable": None,
            "sequence": None,
            "is_valid": False,
            "errors": [],
            "length": len(aju) if aju else 0,
        }

        if not aju:
            result["errors"].append("AJU is empty")
            return result

        if not AJU_PATTERN.match(aju):
            result["errors"].append(
                f"AJU must be 26 digits (got {len(aju)}): {aju!r}"
            )
            return result

        m = AJU_STRUCTURE.match(aju)
        if not m:
            result["errors"].append("Invalid AJU structure")
            return result

        gd = m.groupdict()
        kode_kantor = gd["kode_kantor"]
        kode_dok = gd["kode_dok"]
        niper = gd["niper"]
        tanggal_str = gd["tanggal"]
        sequence = gd["sequence"]

        # Validasi kode_kantor
        if not re.match(r"^\d{4}$", kode_kantor):
            result["errors"].append(f"Invalid kode_kantor: {kode_kantor}")

        # Validasi kode_dok
        if kode_dok not in KODE_DOKUMEN:
            result["errors"].append(f"Unknown kode_dok: {kode_dok}")
        else:
            doc_names = {
                "01": "PIB (Pemberitahuan Impor Barang)",
                "23": "PEB (Pemberitahuan Ekspor Barang)",
                "11": "BC 1.1 (Laporan Impor - FTZ)",
                "12": "BC 1.2 (Laporan Ekspor - FTZ)",
                "15": "BC 1.5 (Laporan Transfer - FTZ)",
                "25": "BC 2.5 (Impor ke FTZ)",
                "27": "BC 2.7 (Transfer FTZ)",
            }
            result["kode_dok_name"] = doc_names.get(kode_dok, kode_dok)

        # Validasi niper
        if not re.match(r"^\d{6}$", niper):
            result["errors"].append(f"Invalid niper: {niper}")

        # Validasi tanggal
        try:
            dt = datetime.strptime(tanggal_str, "%Y%m%d")
            result["tanggal_readable"] = dt.strftime("%Y-%m-%d")
            if dt.date() > datetime.now().date():
                result["errors"].append(
                    f"AJU date is in the future: {result['tanggal_readable']}"
                )
        except ValueError:
            result["errors"].append(f"Invalid date in AJU: {tanggal_str}")

        # Validasi sequence
        try:
            seq_num = int(sequence)
            if not 1 <= seq_num <= 999999:
                result["errors"].append(f"Sequence out of range: {seq_num}")
        except ValueError:
            result["errors"].append(f"Invalid sequence: {sequence}")

        result["kode_kantor"] = kode_kantor
        result["kode_dok"] = kode_dok
        result["niper"] = niper
        result["tanggal"] = tanggal_str
        result["sequence"] = sequence
        result["is_valid"] = len(result["errors"]) == 0

        return result

    @property
    def kode_kantor(self) -> str:
        return self._kode_kantor

    @property
    def niper(self) -> str:
        if self._niper:
            return f"{self._niper[:2]}****"
        return "***NOT SET***"

    @property
    def current_sequence(self) -> int:
        return self._sequence

    def __repr__(self) -> str:
        return (
            f"AJUGenerator(kode_kantor={self._kode_kantor}, "
            f"niper={self.niper}, next_seq={self._sequence})"
        )
    

_DEFAULT_GENERATOR: Optional[AJUGenerator] = None


def get_generator(
    config_path: str = "ml/company_config.json",
) -> AJUGenerator:
    global _DEFAULT_GENERATOR
    if _DEFAULT_GENERATOR is None:
        _DEFAULT_GENERATOR = AJUGenerator(config_path=config_path)
    return _DEFAULT_GENERATOR


def generate_aju(
    document_type: str = "pib",
    shipment_date: Optional[str | date] = None,
    config_path: str = "ml/company_config.json",
) -> str:
    gen = get_generator(config_path)
    return gen.generate_aju(
        document_type=document_type,
        shipment_date=shipment_date,
    )


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("AJU Number Generator — Test Mode")
    print("=" * 60)

    # Try multiple possible config locations
    possible_paths = [
        Path(__file__).parent.parent / "company_config.json",
        Path(__file__).parent.parent / "ml" / "company_config.json",
        Path("ml/company_config.json").resolve(),
        Path("C:/Users/Acer/Documents/Kuliah/Kerja Praktik/Zero-Touch-Customs-Engine/ml/company_config.json"),
    ]
    config_path = None
    for p in possible_paths:
        if p.exists():
            config_path = p
            break

    if config_path is None:
        print(f"\nERROR: company_config.json not found.")
        print("Searched in:")
        for p in possible_paths:
            print(f"  - {p}")
        print("\nPlease create ml/company_config.json with:")
        print("  - ceisa.kode_kantor: 4-digit Kode Kantor BC")
        print("  - ceisa.niper: 6-digit NIPER")
        sys.exit(1)

    try:
        gen = AJUGenerator(config_path=config_path)
        print(f"\nGenerator: {gen}")
        print(f"Configured Kode Kantor: {gen.kode_kantor}")
        print(f"Configured NIPER: {gen.niper}")
        print(f"Next Sequence: {gen.current_sequence}")

        aju = gen.generate_aju(
            document_type="pib",
            shipment_date=datetime.now().strftime("%Y-%m-%d"),
        )
        print(f"\nGenerated AJU: {aju}")
        print(f"Length: {len(aju)} digits")

        validation = AJUGenerator.validate(aju)
        print(f"\nValidation: {'VALID' if validation['is_valid'] else 'INVALID'}")
        print(f"  Kode Kantor  : {validation['kode_kantor']}")
        print(f"  Kode Dokumen : {validation['kode_dok']} ({validation['kode_dok_name']})")
        print(f"  NIPER        : {validation['niper']}")
        print(f"  Tanggal      : {validation['tanggal']} ({validation['tanggal_readable']})")
        print(f"  Sequence     : {validation['sequence']}")

        batch = gen.generate_batch(3, document_type="pib")
        print(f"\nBatch AJU (3):")
        for a in batch:
            print(f"  {a}")

    except AJUValidationError as e:
        print(f"\nERROR: {e}")
        print("\nPlease configure ml/company_config.json with:")
        print("  - ceisa.kode_kantor: 4-digit Kode Kantor BC")
        print("  - ceisa.niper: 6-digit NIPER")
        sys.exit(1)
