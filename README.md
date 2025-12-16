# Resonant Soul

Undertale esintili, sinematik efektlere sahip bir mermi cehennemi mini oyun.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

## Çalıştırma

```bash
python game.py
```

## Sorun Giderme

### `ModuleNotFoundError: No module named 'pygame'`

- Sanal ortam aktifken `python -m pip install -r requirements.txt` komutunu çalıştırarak eksik bağımlılıkları yükleyin.
- Komutu PowerShell içinde çalıştırıyorsanız `py -m pip install -r requirements.txt` kullanabilirsiniz.
- Bağımlılıkları yükledikten sonra oyunu tekrar `python game.py` ile başlatın.

### Özellikler
- Nova Seraph adlı yeni düşmana karşı yoğun savaş.
- HP eşiklerine göre renk paletleri değişen dört benzersiz saldırı fazı ve faz geçişi sinematikleri.
- Dinamik arena animasyonları, yer çekimi mekaniği, hareketli platformlar ve coyote time destekli zıplama.
- Cinematic "FIGHT" kılıç efektleri, renkli lazer yağmuru ve hızınıza tepki veren kalp izi.
- Kaydet/Yükle sistemiyle zorluk bazlı en iyi hayatta kalma süreleri; menüde sürükleyici parıltılar ve yardım paneli (H).
- Hikâye, Zorluk ve Kâbus olmak üzere üç mod ve her mod için skor panosu.
