from flask import Flask, jsonify, request
import pandas as pd
from flask_cors import CORS
import io
import tempfile # Geçici dosya işlemleri için
import os       # Dosya silme işlemleri için

app = Flask(__name__)

# --- CORS Ayarları (Öncekiyle aynı, Netlify adresinizi kontrol edin) ---
NETLIFY_SITE_URL = "https://tahminci.netlify.app" 
origins = [NETLIFY_SITE_URL]
if app.debug:
    origins.append("http://127.0.0.1:5500")
    origins.append("http://localhost:5500")
CORS(app, resources={r"/api/*": {"origins": origins}})
# --- CORS Ayarları Bitişi ---

df_global = None 

@app.route('/api/upload', methods=['POST'])
def upload_file():
    global df_global 
    if 'file' not in request.files:
        return jsonify({"error": "Dosya bulunamadı."}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Dosya seçilmedi."}), 400

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        temp_file_path = None # Geçici dosya yolunu saklamak için
        try:
            # Dosyayı geçici bir dosyaya kaydet
            # delete=False çünkü biz okuduktan sonra manuel sileceğiz
            # NamedTemporaryFile context manager'dan çıkınca dosyayı siler, bu yüzden delete=False önemli
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                file.save(tmp.name) # Flask'ın FileStorage objesinin save metodu
                temp_file_path = tmp.name
            
            # Pandas'ın geçici dosyadan okumasını sağla
            df_temp = pd.read_excel(temp_file_path)
            
            df_temp.columns = df_temp.columns.str.strip()
            
            required_cols = ['İY', 'MS', 'EV SAHİBİ', 'DEPLASMAN', 'MS 1', 'MS 0', 'MS 2'] 
            missing_cols = [col for col in required_cols if col not in df_temp.columns]
            
            if missing_cols:
                return jsonify({"error": f"Yüklenen dosyada eksik sütunlar var: {', '.join(missing_cols)}. Lütfen Excel dosyanızı kontrol edin."}), 400

            df_global = df_temp 
            print(f"'{file.filename}' dosyası başarıyla yüklendi ve işlendi. Boyut: {df_global.shape}")
            return jsonify({"message": "Dosya başarıyla yüklendi ve işlendi.", "shape": list(df_global.shape)}), 200
        
        except Exception as e:
            print(f"Yüklenen dosya işlenirken hata: {e}")
            return jsonify({"error": f"Dosya işlenirken bir hata oluştu: {str(e)}"}), 500
        
        finally:
            # Geçici dosyayı her durumda silmeye çalış
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    print(f"Geçici dosya silindi: {temp_file_path}")
                except Exception as e_remove:
                    print(f"Geçici dosya silinirken hata: {e_remove}")
    else:
        return jsonify({"error": "Geçersiz dosya türü. Lütfen bir Excel dosyası (.xlsx veya .xls) yükleyin."}), 400

# --- /api/upcoming-matches ve /api/analyze-matches fonksiyonları ve diğer kodlar aynı kalır ---
# (calculate_detailed_statistics fonksiyonu dahil)

@app.route('/api/upcoming-matches', methods=['GET'])
def get_upcoming_matches():
    global df_global
    if df_global is None:
        return jsonify({"error": "Lütfen önce bir Excel dosyası yükleyin."}), 400
    
    if 'İY' not in df_global.columns or 'MS' not in df_global.columns:
        return jsonify({"error": "Yüklenen veride 'İY' veya 'MS' sütunları bulunamadı."}), 500

    try:
        upcoming = df_global[pd.isna(df_global['İY']) & pd.isna(df_global['MS'])].copy()
        upcoming = upcoming.where(pd.notnull(upcoming), None) 
        return jsonify(upcoming.to_dict(orient='records'))
    except Exception as e:
        print(f"Oynanacak maçlar alınırken hata: {e}")
        return jsonify({"error": f"Maç verileri işlenirken bir hata oluştu: {str(e)}"}), 500

def calculate_detailed_statistics(matches_df):
    predictions = {}
    if matches_df.empty:
        return predictions

    # total_matches = len(matches_df) # Bu değişken kullanılmıyor gibi, kaldırılabilir

    def parse_score(score_str, separator='-'):
        try:
            if pd.isna(score_str) or score_str is None: return None, None
            parts = str(score_str).split(separator)
            if len(parts) == 2:
                return int(str(parts[0]).strip()), int(str(parts[1]).strip())
            return None, None
        except:
            return None, None

    if 'MS' in matches_df.columns:
        ms_scores = matches_df['MS'].apply(parse_score)
        valid_ms_scores = [s for s in ms_scores if s[0] is not None and s[1] is not None]
        valid_ms_count = len(valid_ms_scores)

        if valid_ms_count > 0:
            ms1_count = sum(1 for h, a in valid_ms_scores if h > a)
            ms0_count = sum(1 for h, a in valid_ms_scores if h == a)
            ms2_count = sum(1 for h, a in valid_ms_scores if h < a)
            predictions['ms_1_percentage'] = (ms1_count / valid_ms_count * 100)
            predictions['ms_1_count'] = ms1_count
            predictions['ms_0_percentage'] = (ms0_count / valid_ms_count * 100)
            predictions['ms_0_count'] = ms0_count
            predictions['ms_2_percentage'] = (ms2_count / valid_ms_count * 100)
            predictions['ms_2_count'] = ms2_count

            total_goals_ms = [h + a for h, a in valid_ms_scores]
            
            alt15_ms_count = sum(1 for tg in total_goals_ms if tg < 1.5)
            ust15_ms_count = valid_ms_count - alt15_ms_count
            predictions['1_5_alt_percentage'] = (alt15_ms_count / valid_ms_count * 100)
            predictions['1_5_alt_count'] = alt15_ms_count
            predictions['1_5_üst_percentage'] = (ust15_ms_count / valid_ms_count * 100) 
            predictions['1_5_üst_count'] = ust15_ms_count
            
            alt25_ms_count = sum(1 for tg in total_goals_ms if tg < 2.5)
            ust25_ms_count = valid_ms_count - alt25_ms_count
            predictions['2_5_alt_percentage'] = (alt25_ms_count / valid_ms_count * 100)
            predictions['2_5_alt_count'] = alt25_ms_count
            predictions['2_5_üst_percentage'] = (ust25_ms_count / valid_ms_count * 100) 
            predictions['2_5_üst_count'] = ust25_ms_count

            alt35_ms_count = sum(1 for tg in total_goals_ms if tg < 3.5)
            ust35_ms_count = valid_ms_count - alt35_ms_count
            predictions['3_5_alt_percentage'] = (alt35_ms_count / valid_ms_count * 100)
            predictions['3_5_alt_count'] = alt35_ms_count
            predictions['3_5_üst_percentage'] = (ust35_ms_count / valid_ms_count * 100) 
            predictions['3_5_üst_count'] = ust35_ms_count

            kgv_count = sum(1 for h, a in valid_ms_scores if h > 0 and a > 0)
            kgy_count = valid_ms_count - kgv_count
            predictions['kgv_percentage'] = (kgv_count / valid_ms_count * 100)
            predictions['kgv_count'] = kgv_count
            predictions['kgy_percentage'] = (kgy_count / valid_ms_count * 100)
            predictions['kgy_count'] = kgy_count
            
            tg_0_1_count = sum(1 for tg in total_goals_ms if tg <= 1)
            tg_2_3_count = sum(1 for tg in total_goals_ms if tg >= 2 and tg <= 3)
            tg_4_6_count = sum(1 for tg in total_goals_ms if tg >= 4 and tg <= 6)
            tg_7_plus_count = sum(1 for tg in total_goals_ms if tg >= 7)
            predictions['tg_0_1_percentage'] = (tg_0_1_count / valid_ms_count * 100)
            predictions['tg_0_1_count'] = tg_0_1_count
            predictions['tg_2_3_percentage'] = (tg_2_3_count / valid_ms_count * 100)
            predictions['tg_2_3_count'] = tg_2_3_count
            predictions['tg_4_6_percentage'] = (tg_4_6_count / valid_ms_count * 100)
            predictions['tg_4_6_count'] = tg_4_6_count
            predictions['tg_7_plus_percentage'] = (tg_7_plus_count / valid_ms_count * 100) 
            predictions['tg_7_plus_count'] = tg_7_plus_count

    if 'İY' in matches_df.columns:
        iy_scores = matches_df['İY'].apply(parse_score)
        valid_iy_scores = [s for s in iy_scores if s[0] is not None and s[1] is not None]
        valid_iy_count = len(valid_iy_scores)

        if valid_iy_count > 0:
            iy1_count = sum(1 for h, a in valid_iy_scores if h > a)
            iy0_count = sum(1 for h, a in valid_iy_scores if h == a)
            iy2_count = sum(1 for h, a in valid_iy_scores if h < a)
            predictions['iy_1_percentage'] = (iy1_count / valid_iy_count * 100)
            predictions['iy_1_count'] = iy1_count
            predictions['iy_0_percentage'] = (iy0_count / valid_iy_count * 100)
            predictions['iy_0_count'] = iy0_count
            predictions['iy_2_percentage'] = (iy2_count / valid_iy_count * 100)
            predictions['iy_2_count'] = iy2_count

            total_goals_iy = [h + a for h, a in valid_iy_scores]

            alt15_iy_count = sum(1 for tg in total_goals_iy if tg < 1.5)
            ust15_iy_count = valid_iy_count - alt15_iy_count
            predictions['iy_1_5a_percentage'] = (alt15_iy_count / valid_iy_count * 100) 
            predictions['iy_1_5a_count'] = alt15_iy_count
            predictions['iy_1_5ü_percentage'] = (ust15_iy_count / valid_iy_count * 100) 
            predictions['iy_1_5ü_count'] = ust15_iy_count
            
    return predictions

@app.route('/api/analyze-matches', methods=['POST'])
def analyze_matches():
    global df_global
    if df_global is None:
        return jsonify({"error": "Lütfen önce bir Excel dosyası yükleyin."}), 400

    try:
        filters = request.json.get('filters', {})
        selected_match_id_str = request.json.get('selected_match_id') # ID frontend'den gelmese bile (undefined -> None)

        past_matches = df_global[pd.notna(df_global['İY']) & pd.notna(df_global['MS'])].copy()
        
        # ID sütunu Excel'de varsa ve frontend'den geçerli bir ID geldiyse, seçili maçı analizden çıkar
        if selected_match_id_str is not None and 'ID' in past_matches.columns:
            try:
                # ID sütununun varlığından emin olduktan sonra numeric yapmayı dene
                if pd.api.types.is_numeric_dtype(past_matches['ID']):
                    selected_match_id = int(selected_match_id_str) 
                    past_matches = past_matches[past_matches['ID'] != selected_match_id]
                else: # Eğer ID sütunu sayısal değilse, string olarak karşılaştır veya bu adımı atla
                    past_matches = past_matches[past_matches['ID'].astype(str) != str(selected_match_id_str)]

            except ValueError:
                print(f"Uyarı: Gelen selected_match_id ('{selected_match_id_str}') ID sütunuyla eşleştirilemedi.")
            except Exception as e: # Daha genel bir hata yakalama
                print(f"ID ile filtreleme sırasında bir hata oluştu: {e}")


        similar_matches = past_matches.copy()

        for key, value_range in filters.items():
            if value_range and key in similar_matches.columns: 
                try:
                    min_val = float(value_range['min'])
                    max_val = float(value_range['max'])
                    # Orijinal sütunu değiştirmeden önce tip dönüşümü yapalım
                    # Ve sadece sayısal olmayan değerleri NaN yapalım, hata vermesini engelleyelim
                    numeric_col = pd.to_numeric(similar_matches[key], errors='coerce')
                    
                    similar_matches = similar_matches[
                        numeric_col.notna() &
                        (numeric_col >= min_val) &
                        (numeric_col <= max_val)
                    ]
                except (ValueError, TypeError) as e:
                    print(f"Uyarı: '{key}' için oran filtresi uygulanırken hata: {e}. Bu filtre atlanıyor.")
                    continue
            
        similar_matches = similar_matches.where(pd.notnull(similar_matches), None)
        calculated_predictions = calculate_detailed_statistics(similar_matches)
        
        analysis_result = {
            "similar_matches": similar_matches.to_dict(orient='records'),
            "summary": {"count": len(similar_matches)},
            "predictions": calculated_predictions 
        }
        return jsonify(analysis_result)

    except Exception as e:
        print(f"Analiz sırasında genel hata: {e}")
        return jsonify({"error": f"Analiz verileri işlenirken bir hata oluştu: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
