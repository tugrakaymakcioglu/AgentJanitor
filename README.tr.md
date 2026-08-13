<div align="center">

<img src="docs/images/banner.png" alt="AgentJanitor - AI Kodlama Ajanı Temizleme ve Teşhis Aracı" width="100%" />

# 🧹 AgentJanitor (Türkçe)

### Yapay Zeka Kodlama Ajanları ve MCP Sunucuları İçin Yerel Sağlık, Teşhis ve Güvenli Temizlik Motoru

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Lisans: Apache-2.0](https://img.shields.io/badge/Lisans-Apache--2.0-0B7285?style=flat-square)](LICENSE)
[![MCP Uyumlu](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-8A2BE2?style=flat-square)](https://modelcontextprotocol.io/)
[![Desteklenen Ajanlar](https://img.shields.io/badge/Ajanlar-Claude%20%7C%20Codex%20%7C%20Gemini%20%7C%20Cursor-orange?style=flat-square)](#-desteklenen-ajanlar)
[![Sıfır Telemetri](https://img.shields.io/badge/Telemetri-Sıfır%20%2F%20%25100%20Yerel-16A34A?style=flat-square)](#-gizlilik-ve-g%C3%BCvenlik-garantileri)

[English README](README.md) &nbsp;·&nbsp; [Kurulum](#-kurulum) &nbsp;·&nbsp; [Hızlı Başlangıç](#-h%C4%B1zl%C4%B1-ba%C5%9Flang%C4%B1%C3%A7) &nbsp;·&nbsp; [Desteklenen Ajanlar](#-desteklenen-ajanlar) &nbsp;·&nbsp; [Güvenlik Modeli](#-g%C3%BCvenlik-modeli)

<br>

**Yapay zeka kodlama ajanlarınız arkalarında RAM tüketen sahipsiz (orphan) süreçler, gigabaytlarca eski oturum geçmişi, bozuk MCP sunucu tanımları ve açıkta kalan API anahtarları bırakır. AgentJanitor bunları yerel olarak teşhis eder ve güvenle temizler.**

</div>

---

## ⚡ Problem: AI Kodlama Ajanlarının Bıraktığı Kalıntılar

AI kodlama ajanları (Claude Code, OpenAI Codex, Gemini CLI, Cursor, Aider, OpenCode) arka planda yüzlerce alt süreç, MCP sunucuları ve önbellek dosyaları oluşturur. Yönetilmediğinde:

- 🛑 **Sahipsiz (Orphaned) Süreçler:** Ana süreç kapansa bile arka planda %100 CPU veya gigabaytlarca RAM tüketen hayalet yardımcı süreçler kalır.
- 💾 **Gigabaytlarca Şişkin Geçmiş:** Oturum geçmişleri, geçici diff'ler ve context önbellekleri SSD'nizi sessizce doldurur.
- 🔌 **Bozuk & Çift MCP Sunucuları:** Silinmiş dizin yolları, yinelenen sunucu tanımları ajanların açılış hızını düşürür.
- 🔑 **Açıkta Kalan Kimlik Bilgileri:** Yapılandırma dosyalarında unutulan düz metin API anahtarları güvenlik riski oluşturur.

---

## ⚖️ Karşılaştırma: AgentJanitor vs Genel Temizleyiciler

| Özellik / Yetenek | Klasik Disk Temizleyicileri | Rastgele Shell Scriptleri | 🧹 **AgentJanitor** |
| :--- | :--- | :--- | :--- |
| **Ajan & MCP Farkındalığı** | ❌ Yok (dosyaları düz bayt görür) | ❌ Statik PID öldürme | ✅ **Özel Ajan ve MCP Adaptörleri** |
| **Aktif Oturum Koruması** | ❌ Körlemesine silme | ❌ Çalışan işi bozar | ✅ **Aktif çalışan işlere asla dokunmaz** |
| **MCP Sağlık ve Tekilleştirme** | ❌ Desteklenmez | ❌ Desteklenmez | ✅ **Statik doğrulama ve yinelenen tespiti** |
| **Kimlik Bilgisi Hijyeni** | ❌ Yok | ❌ Yok | ✅ **Güvenli parmak izli gizli anahtar tarayıcısı** |
| **Geri Alma (Undo) Desteği** | ❌ Kalıcı siler | ❌ Geri alınamaz | ✅ **Otomatik yedek manifestosu + `undo`** |
| **Simülasyon (Dry Run)** | ❌ Nadir | ❌ Yok | ✅ **`--dry-run` ile sıfır riskli önizleme** |
| **Açıklanabilir Sağlık Puanı** | ❌ Yok | ❌ Yok | ✅ **0–100 Deterministik puanlama** |

---

## 🚀 Kurulum

```bash
# uv ile (Önerilen - Ultra Hızlı)
uv tool install agentjanitor

# pipx ile
pipx install agentjanitor

# Standart pip ile
pip install agentjanitor
```

---

## ⚡ Hızlı Başlangıç

```bash
# 1. Zararsız sağlık taraması ve raporlama
agentjanitor scan

# 2. Değişiklik yapmadan temizlik planını önizleyin
agentjanitor fix --dry-run

# 3. Güvenli temizlikleri uygulayın (Sadece SAFE seviyesindeki eylemler yapılır)
agentjanitor fix

# 4. Yüklü ajanlarınız için derin teşhis çalıştırın
agentjanitor doctor

# 5. Son temizlik işlemini tek komutla geri alın
agentjanitor undo
```

---

## 🤖 Desteklenen Ajanlar

| Ajan | Durum | Açıklama |
|---|---|---|
| **Claude Code** | ✅ Tam Destekli | Yapılandırmalar, oturum geçmişi, MCP sunucu analizleri |
| **OpenAI Codex** | ✅ Tam Destekli | Süreç ağacı ve oturum geçmişi keşfi |
| **Gemini CLI** | ⚡ Deneysel | Süreç izleme ve önbellek denetimi |
| **Cursor / Cline / Aider** | 📋 Yol Haritasında (v0.2.0) | Adaptörler geliştirilme aşamasında |

---

## 🛡️ Güvenlik Modeli

1. **Üçlü Doğrulama:** Sadece ölü üst süreç (dead parent) + uzun süre hareketsizlik + yapısal kanıt taşıyan süreçler `CONFIRMED_ORPHANED` olarak işaretlenir.
2. **Aktif Oturumlara Dokunulmaz:** Şu an üzerinde çalışılan bir çalışma alanı asla sonlandırılmaz.
3. **Silme Yerine Arşivleme:** Eski oturumlar doğrudan silinmek yerine sıkıştırılarak arşivlenir.
4. **Tek Tıkla Geri Alma:** Herhangi bir değişiklikten önce otomatik yedek manifestosu oluşturulur; `agentjanitor undo` ile eski haline döner.

---

## 📄 Lisans

Apache-2.0 Lisansı altında dağıtılmaktadır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.
