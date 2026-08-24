"""Spar C: FEATURE BLUEPRINT for dataset_v1.0, byggd fran noll utifran de
frysta Spar A/B-lagren - INTE fran de gamla 48 features och INTE fran de 26
som redan implementerats i forsta Spar C-omgangen.

Legacy (momentum_ml/features/feature_engineering.py FEATURE_COLS,
UTVECKLINGSLOGG.md) anvands ENDAST read-only som completeness-check, sist i
denna fil, for att sakerstalla att ingen informationsdimension glomts bort.
Inget darifran ateranvands automatiskt eller betraktas som validerat.

Varje kandidat dokumenteras med de 11 begarda falten. `status` ar en av:
  IMPLEMENTERAD   - finns redan i Spar C:s 26 falt (fore denna revision)
  NY_BYGGD        - lags till i denna revision (KAN BYGGAS, byggd)
  KAN_BYGGAS      - identifierad, byggbar, INTE byggd denna omgang (dokumenterat gap)
  SAKNAR_DATA     - kraver data Spar A/B inte har
  BOR_INTE_BYGGAS - byggbar men avraddes av principskal
"""
from __future__ import annotations

import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "docs/probes/feature_blueprint.json"

# ============================================================================
# BLUEPRINT
# ============================================================================
BP = []


def lägg(**kw):
    BP.append(kw)


# --------------------------- CORE / PRIS -----------------------------------
lägg(id="mom_4w", familj="CORE/momentum", hypotes="Kortsiktig prismomentum.",
     ravalt=["Spår A: adj"], formel="adj[T]/adj[T-4v]-1", lookback="4v",
     pit="rullande fönster, endast data ≤T", missing="null vid <4v historik",
     survivorship="säkert (Spår A)", redundans="låg", status="IMPLEMENTERAD")
lägg(id="mom_13w", familj="CORE/momentum", hypotes="Medelfristig momentum (ett kvartal).",
     ravalt=["Spår A: adj"], formel="adj[T]/adj[T-13v]-1", lookback="13v",
     pit="rullande fönster, endast data ≤T", missing="null vid <13v historik",
     survivorship="säkert", redundans="låg (delvis mot mom_4w)", status="IMPLEMENTERAD")
lägg(id="mom_26w", familj="CORE/momentum", hypotes="Halvårsmomentum.",
     ravalt=["Spår A: adj"], formel="adj[T]/adj[T-26v]-1", lookback="26v",
     pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="medel (mot 13w/52w)", status="IMPLEMENTERAD")
lägg(id="mom_52w", familj="CORE/momentum", hypotes="Standard 12-månadersmomentum.",
     ravalt=["Spår A: adj"], formel="adj[T]/adj[T-52v]-1", lookback="52v",
     pit="rullande fönster, endast data ≤T", missing="null vid <52v historik (0% 2020, förväntat)",
     survivorship="säkert", redundans="medel (mot 26w/12-1)", status="IMPLEMENTERAD")
lägg(id="mom_12_1", familj="CORE/momentum", hypotes="12-1-momentum, exkl. senaste månaden (undviker kortsiktig reversering).",
     ravalt=["Spår A: adj"], formel="adj[T-4v]/adj[T-52v]-1", lookback="52v",
     pit="rullande fönster, endast data ≤T", missing="null vid <52v historik",
     survivorship="säkert", redundans="hög mot mom_52w (delar 90%+ fönster)", status="IMPLEMENTERAD")
lägg(id="mom_relative_index_52w", familj="CORE/relativt momentum", status="NY_BYGGD",
     hypotes="Momentum RELATIVT marknaden — särskiljer bolagsspecifik styrka från allmän uppgång.",
     ravalt=["Spår A: adj (instrument + egenbyggt likaviktat index)"],
     formel="mom_52w[instrument] - mom_52w[index]", lookback="52v",
     pit="indexet byggs PIT-dynamiskt (endast instrument noterade vid T ingår)",
     missing="null om instrumentets egen mom_52w saknas",
     redundans="medel mot mom_52w (skillnadstermen adderar info men delar bas)")
lägg(id="mom_relative_sector_52w", familj="CORE/relativt momentum", status="KAN_BYGGAS",
     hypotes="Momentum relativt sektormedian — särskiljer bolag från branschtrend.",
     ravalt=["Spår A: adj", "Börsdata sectorId (instruments_live.json, EJ PIT-rekonstruerad)"],
     formel="mom_52w[instrument] - median(mom_52w, samma sectorId, samma T)", lookback="52v",
     pit="sektortillhörighet är STATISK (dagens klassificering appliceras retroaktivt) — samma "
        "kända begränsning som redan dokumenterad för marknadssegment i Spår C",
     missing="null om <5 instrument i samma sektor har giltig mom_52w vid T (för få för en "
            "meningsfull median)",
     redundans="hög mot mom_relative_index_52w — bedöms INTE byggas denna omgång för att "
               "undvika dubblering av samma grundidé med en svagare PIT-egenskap")
lägg(id="residual_momentum_52w", familj="CORE/residual momentum", status="NY_BYGGD",
     hypotes="Momentum i AVKASTNING SOM INTE FÖRKLARAS av marknadsexponering (beta) — legacy "
            "hade en egen version (resid_mom), men denna byggs oberoende från grunden.",
     ravalt=["Spår A: adj (instrument + index)"],
     formel="kumulativ residual (stock_ret - beta_52w*index_ret) över 52v, beta skattad "
           "rullande på samma fönster",
     lookback="52v (samma fönster som beta_52w)",
     pit="rullande regression, endast data ≤T", missing="null om beta_52w saknas",
     survivorship="säkert (index byggt enbart av Spår A)",
     redundans="medel mot mom_relative_index_52w (samma hypotes, mer sofistikerad metod)")
lägg(id="trend_strength_52w", familj="CORE/trend", status="NY_BYGGD",
     hypotes="Hur STARK och konsekvent är trenden — t-stat för en linjär regressions lutning "
            "särskiljer en jämn uppgång från en volatil sicksack med samma totalavkastning.",
     ravalt=["Spår A: adj"], formel="t-stat för lutningen i OLS(log(adj) ~ tid), trailing 52v",
     lookback="52v", pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="låg — kompletterar mom_52w, mäter FORM inte NIVÅ")
lägg(id="trend_consistency_52w", familj="CORE/trend", status="NY_BYGGD",
     hypotes="Andel positiva veckor i trenden — robust mot enskilda extremveckor, till "
            "skillnad från trend_strength som är känslig för outliers.",
     ravalt=["Spår A: adj"], formel="andel veckor med positiv veckoavkastning, trailing 52v",
     lookback="52v", pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="medel mot trend_strength_52w")
lägg(id="momentum_acceleration_13w", familj="CORE/momentum", status="NY_BYGGD",
     hypotes="Accelererar eller bromsar momentumet — andraderivata, tidig varningssignal.",
     ravalt=["Spår A: adj"], formel="mom_13w[T] - mom_13w[T-13v]", lookback="26v (två 13v-fönster)",
     pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="låg — mäter förändringstakt, inte nivå")
lägg(id="reversal_1w", familj="CORE/kortsiktig reversal", status="NY_BYGGD",
     hypotes="Kortsiktig överreaktion — senaste veckans avkastning tenderar reversera "
            "(motsatt riktning mot mom_4w/mom_13w).",
     ravalt=["Spår A: adj"], formel="-(adj[T]/adj[T-1v]-1)", lookback="1v",
     pit="rullande fönster, endast data ≤T", missing="null vid <1v historik",
     survivorship="säkert", redundans="låg, ortogonal hypotes mot momentum-familjen")
lägg(id="price_vs_sma26w", familj="CORE/trend", status="IMPLEMENTERAD",
     hypotes="Avstånd till glidande medelvärde — klassisk trendföljning.", ravalt=["Spår A: adj"],
     formel="adj[T]/mean(adj,26v)-1", lookback="26v", pit="rullande fönster",
     missing="null vid <26v historik", survivorship="säkert", redundans="medel mot mom_26w")
lägg(id="price_vs_sma52w", familj="CORE/trend", status="IMPLEMENTERAD",
     hypotes="Långsiktig trendföljning.", ravalt=["Spår A: adj"],
     formel="adj[T]/mean(adj,52v)-1", lookback="52v", pit="rullande fönster",
     missing="null vid <52v historik", survivorship="säkert", redundans="medel mot mom_52w/"
             "trend_strength_52w")
lägg(id="high52w_ratio", familj="CORE/distance-to-high", status="IMPLEMENTERAD",
     hypotes="Närhet till 52-veckorshögsta — dokumenterad ankareffekt.",
     ravalt=["Spår A: adj"], formel="adj[T]/max(adj,52v)", lookback="52v",
     pit="rullande fönster", missing="null vid <52v historik", survivorship="säkert", redundans="låg")
lägg(id="low52w_ratio", familj="CORE/distance-to-high (invers)", status="IMPLEMENTERAD",
     hypotes="Avstånd till 52-veckorslägsta.", ravalt=["Spår A: adj"],
     formel="adj[T]/min(adj,52v)", lookback="52v", pit="rullande fönster",
     missing="null vid <52v historik", survivorship="säkert", redundans="hög mot high52w_ratio")
lägg(id="drawdown_current_104w", familj="CORE/drawdown & recovery", status="NY_BYGGD",
     hypotes="Aktuell nedgång från toppen — bredare fönster (104v) än high52w_ratio för att "
            "fånga längre cykler, inte bara senaste året.",
     ravalt=["Spår A: adj"], formel="adj[T]/max(adj,104v)-1", lookback="104v",
     pit="rullande fönster, endast data ≤T", missing="null vid <52v historik (partiellt fönster "
        "tillåtet, samma tröskel som andra 52v-mått)",
     survivorship="säkert", redundans="medel mot high52w_ratio (samma idé, längre fönster)")
lägg(id="max_drawdown_52w", familj="CORE/drawdown & recovery", status="NY_BYGGD",
     hypotes="Värsta realiserade toppen-till-botten-nedgången i fönstret — en ren riskstatistik, "
            "skild från VAR man befinner sig nu (drawdown_current).",
     ravalt=["Spår A: adj"], formel="min över fönstret av (adj[t]/running_max(adj)[t] - 1)",
     lookback="52v", pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="låg — kompletterar vol_52w med ett annat riskmått")
lägg(id="risk_adj_momentum_52w", familj="CORE/riskjusterat momentum", status="NY_BYGGD",
     hypotes="Momentum per enhet risk — ett Sharpe-liknande mått som separerar 'stabil uppgång' "
            "från 'volatil uppgång' med samma totalavkastning.",
     ravalt=["Spår A: adj (via redan byggda mom_52w, vol_52w)"],
     formel="mom_52w / vol_52w", lookback="52v",
     pit="ärver PIT från komponenterna", missing="null om vol_52w=0 eller endera komponent null",
     survivorship="säkert", redundans="HÖG — kvot av två redan befintliga features, dokumenteras "
                 "trots detta eftersom kvoten inte är en linjär kombination en trädmodell "
                 "trivialt kan återskapa")

# ------------------------------- RISK ---------------------------------------
lägg(id="vol_13w", familj="RISK/volatilitet", status="IMPLEMENTERAD",
     hypotes="Realiserad volatilitet, medelfristig.", ravalt=["Spår A: adj"],
     formel="std(veckoavkastningar, 13v)", lookback="13v", pit="rullande fönster",
     missing="null vid <8v historik", survivorship="säkert", redundans="låg")
lägg(id="vol_52w", familj="RISK/volatilitet", status="IMPLEMENTERAD",
     hypotes="Realiserad volatilitet, långsiktig — lågvolatilitetsanomalin.", ravalt=["Spår A: adj"],
     formel="std(veckoavkastningar, 52v)", lookback="52v", pit="rullande fönster",
     missing="null vid <26v historik", survivorship="säkert", redundans="medel mot vol_13w")
lägg(id="vol_4w", familj="RISK/volatilitet", status="KAN_BYGGAS",
     hypotes="Mycket kortsiktig volatilitet — fångar akut osäkerhet (t.ex. kring en händelse) "
            "som 13v/52v-måtten utspäder.",
     ravalt=["Spår A: adj"], formel="std(dagliga avkastningar, 4v)", lookback="4v",
     pit="rullande fönster, endast data ≤T", missing="null vid <3v historik",
     redundans="hög mot vol_13w — INTE byggd denna omgång, marginell tilläggsinformation")
lägg(id="downside_vol_52w", familj="RISK/downside volatility", status="NY_BYGGD",
     hypotes="Semi-deviation — bestraffar bara nedsidan, i linje med hur investerare faktiskt "
            "upplever risk (uppsidesvolatilitet är inte 'risk' i samma mening).",
     ravalt=["Spår A: adj"], formel="std(veckoavkastningar < 0, 52v)", lookback="52v",
     pit="rullande fönster, endast data ≤T", missing="null vid <10 negativa veckor i fönstret",
     survivorship="säkert", redundans="medel mot vol_52w, men ortogonal hypotes (symmetrisk vs "
                 "asymmetrisk risk)")
lägg(id="beta_52w", familj="RISK/beta", status="NY_BYGGD",
     hypotes="Systematisk marknadsexponering — klassisk riskfaktor, grund för residual momentum "
            "och idiosynkratisk volatilitet.",
     ravalt=["Spår A: adj (instrument + egenbyggt index)"],
     formel="cov(stock_ret, index_ret)/var(index_ret), rullande 52v veckoavkastningar",
     lookback="52v", pit="rullande regression, endast data ≤T", missing="null vid <26v historik "
             "eller om index_ret saknar varians",
     survivorship="säkert (index byggt enbart av Spår A)", redundans="låg")
lägg(id="idio_vol_52w", familj="RISK/idiosynkratisk volatilitet", status="NY_BYGGD",
     hypotes="Volatilitet EFTER att marknadsexponeringen räknats bort — bolagsspecifik risk, "
            "dokumenterad egen anomali skild från total volatilitet.",
     ravalt=["Spår A: adj (instrument + index, via beta_52w)"],
     formel="std(residualer från stock_ret = alpha + beta*index_ret), rullande 52v",
     lookback="52v", pit="rullande regression, endast data ≤T", missing="null om beta_52w saknas",
     survivorship="säkert", redundans="medel mot vol_52w (delmängd av total volatilitet)")
lägg(id="skew_52w", familj="RISK/skew", status="NY_BYGGD",
     hypotes="Snedhet i avkastningsfördelningen — negativ skew (krascher) prissätts annorlunda "
            "än positiv skew (lotteriliknande uppsida), dokumenterad egen faktor.",
     ravalt=["Spår A: adj"], formel="skewness(veckoavkastningar, 52v)", lookback="52v",
     pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="låg")
lägg(id="skew_13w", familj="RISK/skew", status="KAN_BYGGAS",
     hypotes="Samma som skew_52w men kortare horisont — fångar akut asymmetri.",
     ravalt=["Spår A: adj"], formel="skewness(veckoavkastningar, 13v)", lookback="13v",
     redundans="hög mot skew_52w — INTE byggd denna omgång, en horisontvariant räcker för att "
               "täcka familjen")
lägg(id="kurtosis_52w", familj="RISK/tail risk", status="NY_BYGGD",
     hypotes="Överskottskurtosis — 'fat tails', hur ofta extremveckor inträffar utöver vad en "
            "normalfördelning skulle ge.",
     ravalt=["Spår A: adj"], formel="excess kurtosis(veckoavkastningar, 52v)", lookback="52v",
     pit="rullande fönster, endast data ≤T", missing="null vid <26v historik",
     survivorship="säkert", redundans="medel mot vol_52w/skew_52w, men mäter en distinkt "
                 "distributionsegenskap (svansmassa, inte spridning eller riktning)")
lägg(id="adx_atr_familjen", familj="RISK/trendstyrka (teknisk)", status="SAKNAR_DATA",
     hypotes="Average Directional Index / Average True Range — klassiska teknisk-analys-mått "
            "på trendstyrka och volatilitet.",
     ravalt=["KRÄVER high/low — Spår A:s VALIDATED-lager innehåller ENDAST {datum, "
            "adjusted_close, volym} (R1 i manifest_sparA.json). Rå OHLC finns i EODHD-arkivet "
            "men togs medvetet INTE med i VALIDATED."],
     formel="—", lookback="—", pit="—",
     missing="hela familjen otillgänglig utan att öppna om och bygga om Spår A",
     redundans="—",
     anmarkning="trend_strength_52w (regressionslutningens t-stat) är den close-baserade "
                "motsvarigheten som ÄR byggd — den fångar en snarlik hypotes utan att kräva OHLC")

# ---------------------------- VOLYM / LIKVIDITET -----------------------------
lägg(id="turnover_13w_msek", familj="VOLYM/traded value", status="IMPLEMENTERAD",
     hypotes="Likviditetsproxy — genomsnittlig daglig omsättning.", ravalt=["Spår A: adj, v"],
     formel="mean(adj*v, 13v)/1e6", lookback="13v", pit="rullande fönster",
     missing="null vid <13v historik", survivorship="säkert", redundans="låg")
lägg(id="volume_trend_13w", familj="VOLYM/volymtrend", status="IMPLEMENTERAD",
     hypotes="Ökande handelsintresse föregår ofta prisrörelse.", ravalt=["Spår A: v"],
     formel="mean(v,4v)/mean(v,föreg.9v)-1", lookback="13v", pit="rullande fönster",
     missing="null vid <13v historik", survivorship="säkert", redundans="medel mot "
             "abnormal_volume_1w (samma grundidé, olika tidsupplösning)")
lägg(id="abnormal_volume_1w", familj="VOLYM/abnormal volume", status="KAN_BYGGAS",
     hypotes="Volymspik relativt eget normalläge — punktdetektor, till skillnad från "
            "volume_trend_13w:s glidande jämförelse.",
     ravalt=["Spår A: v"], formel="v[senaste v]/mean(v,trailing 13v)", lookback="13v",
     redundans="hög mot volume_trend_13w — INTE byggd denna omgång, marginell tilläggsinfo "
               "utöver den redan byggda glidande varianten")
lägg(id="illiquidity_amihud_13w", familj="VOLYM/illikviditet", status="NY_BYGGD",
     hypotes="Amihud illikviditetsmått — hur mycket rör sig priset per omsatt krona. Klassisk, "
            "väldokumenterad likviditetspremiefaktor, skild från ren omsättningsnivå.",
     ravalt=["Spår A: adj, v"], formel="mean(|dagsavkastning|/(adj*v), 13v)", lookback="13v",
     pit="rullande fönster, endast data ≤T", missing="null vid <13v historik eller v=0 alla dagar",
     survivorship="säkert", redundans="medel mot turnover_13w_msek (relaterad men egen "
                 "väletablerad definition, inte bara samma mått omvänt)")
lägg(id="price_volume_corr_13w", familj="VOLYM/pris-volym-interaktion", status="KAN_BYGGAS",
     hypotes="Samvariation mellan avkastning och volym — svagare, mer explorativ hypotes än "
            "övriga volymmått.",
     ravalt=["Spår A: adj, v"], formel="corr(dagsavkastning, volym, 13v)", lookback="13v",
     redundans="låg mot övriga, men hypotesen är svag/explorativ — INTE byggd denna omgång, "
               "prioriterad lägre än de mer väletablerade måtten ovan")

# ------------------------ RELATIVA / CROSS-SECTIONAL -------------------------
lägg(id="egenbyggt_likaviktat_index", familj="RELATIVT/infrastruktur", status="NY_BYGGD",
     hypotes="Inte en feature i sig — ett internt marknadsproxy-index, likaviktat över "
            "PIT-dynamiskt noterade CORE-instrument, som grund för samtliga relativa/beta-mått. "
            "Ingen extern indexserie (t.ex. OMXSPI) finns validerad i Spår A.",
     ravalt=["Spår A: adj, samtliga 404 instrument"],
     formel="likaviktat medelvärde av veckoavkastningar över instrument noterade vid respektive "
           "vecka", lookback="—", pit="PIT-dynamisk medlemskap (endast instrument med giltigt "
           "pris den veckan ingår)", missing="aldrig — index existerar så länge ≥1 instrument har "
           "data", survivorship="säkert (byggt enbart av Spår A:s survivorship-säkra serier)",
     redundans="—", ej_feature=True)
lägg(id="rank_mom_52w_pct", familj="RELATIVT/cross-sectional rank", status="NY_BYGGD",
     hypotes="Tvärsnittsrang är ofta mer robust än råvärdet för ranking-uppgifter — mindre "
            "känslig för regimskiften i absolut avkastningsnivå.",
     ravalt=["Spår C: mom_52w (samtliga instrument, samma panel_date)"],
     formel="percentilrang av mom_52w bland alla instrument med giltigt värde samma panel_date",
     lookback="0 (tvärsnittstransform, ingen egen historik)",
     pit="beräknas per panel_date över samtidiga observationer — läcker inte över tid",
     missing="null om mom_52w saknas", survivorship="säkert",
     redundans="hög mot mom_52w (monoton transform) men ekonomiskt motiverad för "
               "rankingmodeller specifikt")
lägg(id="rank_vol_52w_pct", familj="RELATIVT/cross-sectional rank", status="KAN_BYGGAS",
     hypotes="Samma resonemang som rank_mom_52w_pct, applicerat på volatilitet.",
     ravalt=["Spår C: vol_52w"], formel="percentilrang av vol_52w per panel_date",
     redundans="hög mot vol_52w — INTE byggd denna omgång; en representant "
               "(rank_mom_52w_pct) räcker för att visa mönstret är byggbart, fler "
               "rangtransformer läggs till om en modell visar behov")
lägg(id="mom_relative_sector_52w_industri", familj="RELATIVT/industrirelativt", status="SAKNAR_DATA",
     hypotes="Momentum relativt branschnivå (branchId, finare upplösning än sectorId).",
     ravalt=["Börsdata branchId finns (instruments_live.json) men delar samma icke-PIT-problem "
            "som sectorId OCH har för få instrument per bransch (404 instrument fördelade på "
            "betydligt fler branscher än sektorer) för att ge stabila medianer"],
     formel="—", lookback="—", pit="—",
     missing="för gles branschindelning i detta universum för att vara meningsfull",
     redundans="—")

# ------------------------------- FUNDAMENTA ----------------------------------
lägg(id="revenue_growth_yoy", familj="FUNDAMENTA/tillväxt", status="IMPLEMENTERAD",
     hypotes="Omsättningstillväxt, TTM mot TTM.", ravalt=["Spår B R12: revenues"],
     formel="rev[T]/rev[T-52v]-1", lookback="52v (två as-of-punkter)",
     pit="as-of report_date≤T för båda punkterna", missing="null om endera punkt saknas ELLER "
        "misslyckas materialitetstestet (§ materialitetsregel)", survivorship="EJ säkert (67/68 "
        "avnoterade saknar data)", redundans="låg",
     anmarkning="TIDIGARE KRÄVER ÅTGÄRD, nu löst med materialitetsregel — se rapport §5")
lägg(id="eps_growth_yoy", familj="FUNDAMENTA/tillväxt", status="IMPLEMENTERAD",
     hypotes="Resultattillväxt per aktie, splitverifierad källa.", ravalt=["Spår B R12: "
            "earnings_Per_Share, profit_To_Equity_Holders, total_Assets"],
     formel="EPS[T]/EPS[T-52v]-1 (samma tecken krävs)", lookback="52v",
     pit="as-of report_date≤T", missing="null vid tecken­olikhet ELLER materialitetstest ej "
        "uppfyllt", survivorship="EJ säkert", redundans="låg",
     anmarkning="TIDIGARE KRÄVER ÅTGÄRD, nu löst med materialitetsregel")
lägg(id="gross_margin_ttm", familj="FUNDAMENTA/lönsamhet", status="IMPLEMENTERAD",
     hypotes="Prissättningsmakt/kostnadsstruktur.", ravalt=["Spår B R12: gross_Income, revenues, "
            "total_Assets"], formel="gross_Income/revenues, materialitetsgated", lookback="0 "
            "(punktmått, senaste R12)", pit="as-of report_date≤T", missing="null om "
            "materialitetstest ej uppfyllt", survivorship="EJ säkert", redundans="hög mot "
            "operating_margin_ttm/net_margin_ttm (delar täljare/nämnare-struktur)",
     anmarkning="TIDIGARE KRÄVER ÅTGÄRD, nu löst")
lägg(id="operating_margin_ttm", familj="FUNDAMENTA/lönsamhet", status="IMPLEMENTERAD",
     hypotes="Rörelselönsamhet.", ravalt=["Spår B R12: operating_Income, revenues, total_Assets"],
     formel="operating_Income/revenues, materialitetsgated", lookback="0", pit="as-of report_date≤T",
     missing="null om materialitetstest ej uppfyllt", survivorship="EJ säkert",
     redundans="hög mot gross_margin_ttm/net_margin_ttm", anmarkning="löst")
lägg(id="net_margin_ttm", familj="FUNDAMENTA/lönsamhet", status="IMPLEMENTERAD",
     hypotes="Nettolönsamhet.", ravalt=["Spår B R12: profit_To_Equity_Holders, revenues, "
            "total_Assets"], formel="profit_To_Equity_Holders/revenues, materialitetsgated",
     lookback="0", pit="as-of report_date≤T", missing="null om materialitetstest ej uppfyllt",
     survivorship="EJ säkert", redundans="hög mot övriga marginalmått", anmarkning="löst")
lägg(id="fcf_margin_ttm", familj="FUNDAMENTA/kassaflödeskvalitet", status="IMPLEMENTERAD",
     hypotes="Kassaflödeskvalitet — skiljer redovisad vinst från verkligt kassaflöde.",
     ravalt=["Spår B R12: free_Cash_Flow, revenues, total_Assets"],
     formel="free_Cash_Flow/revenues, materialitetsgated", lookback="0", pit="as-of report_date≤T",
     missing="null om materialitetstest ej uppfyllt", survivorship="EJ säkert",
     redundans="medel mot net_margin_ttm", anmarkning="löst")
lägg(id="ocf_margin_ttm", familj="FUNDAMENTA/kassaflödeskvalitet", status="NY_BYGGD",
     hypotes="Operativt kassaflöde relativt omsättning — parallell till fcf_margin men FÖRE "
            "investeringar, skiljer drift från kapitalintensitet.",
     ravalt=["Spår B R12: cash_Flow_From_Operating_Activities, revenues, total_Assets"],
     formel="cash_Flow_From_Operating_Activities/revenues, materialitetsgated", lookback="0",
     pit="as-of report_date≤T", missing="null om materialitetstest ej uppfyllt",
     survivorship="EJ säkert", redundans="hög mot fcf_margin_ttm (skiljer sig bara med capex)")
lägg(id="roe_ttm", familj="FUNDAMENTA/lönsamhet", status="IMPLEMENTERAD",
     hypotes="Lönsamhet på eget kapital.", ravalt=["Spår B R12: profit_To_Equity_Holders, "
            "total_Equity"], formel="profit_To_Equity_Holders/total_Equity", lookback="0",
     pit="as-of report_date≤T", missing="null om total_Equity=0/saknas", survivorship="EJ säkert",
     redundans="medel mot roa_ttm")
lägg(id="roa_ttm", familj="FUNDAMENTA/lönsamhet", status="IMPLEMENTERAD",
     hypotes="Lönsamhet på totalt kapital, mindre känslig för belåning.",
     ravalt=["Spår B R12: profit_To_Equity_Holders, total_Assets"],
     formel="profit_To_Equity_Holders/total_Assets", lookback="0", pit="as-of report_date≤T",
     missing="null om total_Assets=0/saknas", survivorship="EJ säkert", redundans="medel mot roe_ttm")
lägg(id="roic_proxy_ttm", familj="FUNDAMENTA/kapitaleffektivitet", status="NY_BYGGD",
     hypotes="Avkastning på investerat kapital — approximation UTAN skattejustering (ingen "
            "explicit skattefältvariabel bland de 22 godkända Spår B-fälten), dokumenterad "
            "begränsning.",
     ravalt=["Spår B R12: operating_Income, total_Equity, net_Debt"],
     formel="operating_Income/(total_Equity+net_Debt)", lookback="0", pit="as-of report_date≤T",
     missing="null om (total_Equity+net_Debt)≤0", survivorship="EJ säkert",
     redundans="medel mot roa_ttm/roe_ttm",
     anmarkning="FÖRE-skatt-approximation, inte sann NOPAT/ROIC — dokumenterad brist")
lägg(id="net_debt_to_equity", familj="FUNDAMENTA/leverage", status="IMPLEMENTERAD",
     hypotes="Finansiell risk/belåningsgrad.", ravalt=["Spår B R12: net_Debt, total_Equity"],
     formel="net_Debt/total_Equity", lookback="0", pit="as-of report_date≤T",
     missing="null om total_Equity=0/saknas. Negativt=nettokassa, giltigt.",
     survivorship="EJ säkert", redundans="låg")
lägg(id="equity_ratio_ttm", familj="FUNDAMENTA/balance-sheet strength", status="NY_BYGGD",
     hypotes="Soliditet — andel av tillgångarna finansierad med eget kapital, ett annat "
            "perspektiv på finansiell styrka än skuldkvoten.",
     ravalt=["Spår B R12: total_Equity, total_Assets"], formel="total_Equity/total_Assets",
     lookback="0", pit="as-of report_date≤T", missing="null om total_Assets=0/saknas",
     survivorship="EJ säkert", redundans="medel mot net_debt_to_equity (samma balansräkning, "
                 "annan skalning)")
lägg(id="current_ratio", familj="FUNDAMENTA/balance-sheet strength", status="IMPLEMENTERAD",
     hypotes="Kortsiktig likviditet.", ravalt=["Spår B R12: current_Assets, current_Liabilities"],
     formel="current_Assets/current_Liabilities", lookback="0", pit="as-of report_date≤T",
     missing="null om current_Liabilities=0/saknas", survivorship="EJ säkert", redundans="låg")
lägg(id="asset_turnover_ttm", familj="FUNDAMENTA/kapitaleffektivitet", status="NY_BYGGD",
     hypotes="Hur effektivt tillgångarna genererar försäljning — DuPont-komponent, skild "
            "hypotes från lönsamhetsmarginalerna (effektivitet, inte marginal).",
     ravalt=["Spår B R12: revenues, total_Assets"], formel="revenues/total_Assets", lookback="0",
     pit="as-of report_date≤T", missing="null om total_Assets=0/saknas", survivorship="EJ säkert",
     redundans="låg mot marginalmåtten, men delar materialitetsproblemet (låg omsättning -> "
               "lågt värde, inte samma extremriktning som marginalerna)")
lägg(id="accruals_ttm", familj="FUNDAMENTA/earnings quality", status="NY_BYGGD",
     hypotes="Sloan accruals — skillnaden mellan redovisad vinst och kassaflöde relativt "
            "tillgångar. Väldokumenterad, oberoende kvalitetsfaktor (hög periodisering "
            "förknippas historiskt med sämre framtida avkastning).",
     ravalt=["Spår B R12: profit_To_Equity_Holders, cash_Flow_From_Operating_Activities, "
            "total_Assets"],
     formel="(profit_To_Equity_Holders - cash_Flow_From_Operating_Activities)/total_Assets",
     lookback="0", pit="as-of report_date≤T", missing="null om total_Assets=0/saknas",
     survivorship="EJ säkert", redundans="låg — explicit efterfrågad familjemedlem, ingen "
                 "nuvarande motsvarighet")
lägg(id="cash_conversion_ttm", familj="FUNDAMENTA/earnings quality", status="KAN_BYGGAS",
     hypotes="Blir redovisad vinst till kassa? Kompletterar accruals_ttm med ett kvotmått.",
     ravalt=["Spår B R12: free_Cash_Flow, profit_To_Equity_Holders, total_Assets"],
     formel="free_Cash_Flow/profit_To_Equity_Holders, materialitetsgated på vinstbasen",
     redundans="hög mot accruals_ttm (samma underliggande hypotes, kvot i stället för "
               "differens) — INTE byggd denna omgång, accruals_ttm bedöms räcka för familjen")
lägg(id="shares_growth_yoy", familj="FUNDAMENTA/dilution", status="NY_BYGGD",
     hypotes="Aktieutspädning eller återköp — explicit efterfrågad, HELT SAKNAD i de "
            "ursprungliga 26 fälten trots att number_Of_Shares är ett godkänt Spår B-fält.",
     ravalt=["Spår B R12: number_Of_Shares"], formel="shares[T]/shares[T-52v]-1", lookback="52v",
     pit="as-of report_date≤T för båda punkterna", missing="null om endera punkt saknas",
     survivorship="EJ säkert", redundans="låg — helt ny informationsdimension")
lägg(id="dividend_yield_ttm", familj="FUNDAMENTA/dividends", status="IMPLEMENTERAD",
     hypotes="Direktavkastning, standard värdefaktor.", ravalt=["Spår B R12: dividend", "Spår A: adj"],
     formel="dividend_TTM/adj[T]", lookback="0", pit="as-of report_date≤T + samtidigt pris",
     missing="null om ingen rapport; 0 är giltigt (delar inte ut)", survivorship="EJ säkert",
     redundans="låg")
lägg(id="dividend_growth_yoy", familj="FUNDAMENTA/dividend growth", status="BOR_INTE_BYGGAS",
     hypotes="Utdelningstillväxt YoY.", ravalt=["Spår B R12: dividend (två as-of-punkter)"],
     formel="div[T]/div[T-52v]-1", lookback="52v",
     missing="odefinierat när div[T-52v]=0 (vanligt — ~40% av rader har dividend=0 enligt "
            "FUNDAMENTAL_QA.md §9)",
     anmarkning="AVRÅDES: en tillväxtprocent från nollbas är antingen odefinierad (division "
                "med noll) eller oändlig (första utdelningen någonsin) — ekonomiskt är detta "
                "en DISKRET händelse ('började dela ut'), inte en kontinuerlig tillväxttakt. "
                "Att tvinga in det i en %-kvot vore att skapa exakt den nära-noll-bas-patologi "
                "materialitetsregeln (§5) just infördes för att undvika. En framtida "
                "'dividend_initiation'-DUMMY vore rätt verktyg, inte en tillväxtkvot.")
lägg(id="fcf_yield_ttm", familj="FUNDAMENTA/värdering", status="NY_BYGGD",
     hypotes="Fritt kassaflöde relativt börsvärde — en genuin värderingsfaktor, HELT SAKNAD "
            "informationsdimension i de ursprungliga 26 (ingen värderingskvot fanns alls).",
     ravalt=["Spår B R12: free_Cash_Flow, number_Of_Shares", "Spår A: adj"],
     formel="free_Cash_Flow / (adj[T]*number_Of_Shares)  (börsvärde i MSEK = pris×miljoner "
           "aktier, enheter matchar utan konvertering)",
     lookback="0", pit="as-of report_date≤T + samtidigt pris",
     missing="null om börsvärde≤0 eller FCF saknas", survivorship="EJ säkert",
     redundans="låg — ny familj (värdering) helt frånvarande innan")
lägg(id="margin_change_operating_yoy", familj="FUNDAMENTA/margin change", status="KAN_BYGGAS",
     hypotes="Förändring i rörelsemarginal YoY, mätt som DIFFERENS (procentenheter) snarare än "
            "kvot — sidosteppar delvis nära-noll-bas-patologin eftersom en differens inte "
            "exploderar på samma sätt som en tillväxtkvot, men de underliggande marginalnivåerna "
            "kräver ändå materialitetsgrind var för sig.",
     ravalt=["Spår C: operating_margin_ttm (två as-of-punkter)"],
     formel="operating_margin_ttm[T] - operating_margin_ttm[T-52v]", lookback="52v",
     redundans="hög mot operating_margin_ttm + revenue_growth_yoy tillsammans — INTE byggd "
               "denna omgång, dokumenterat gap")
lägg(id="growth_acceleration_yoy", familj="FUNDAMENTA/growth acceleration", status="KAN_BYGGAS",
     hypotes="Accelererar eller bromsar omsättningstillväxten — kräver TRE as-of-punkter "
            "(T, T-52v, T-104v).",
     ravalt=["Spår B R12: revenues (tre as-of-punkter)"],
     formel="revenue_growth_yoy[T] - revenue_growth_yoy[T-52v]", lookback="104v",
     missing="271/355 instrument har tillräcklig R12-historik (≥2019) för att ge T-104v från "
            "panelens tidiga år; övriga får null där",
     redundans="låg — egen informationsdimension",
     anmarkning="INTE byggd denna omgång: otillräcklig historik för fullständig "
                "panelperiodstäckning (2020–2021) dokumenteras som ett gap snarare än att "
                "byggas med kraftigt nedsatt tidig täckning")

# --------------------------------- EVENT/REGIM --------------------------------
lägg(id="return_since_last_report_ttm", familj="EVENT/rapportrelaterat", status="NY_BYGGD",
     hypotes="Post-earnings-announcement drift (PEAD) — kumulativ avkastning sedan senaste "
            "rapporten. Ersätter MEDVETET legacyns attention_gap/interact_report_reaction, "
            "som hade ett obegränsat 1/(vol_ratio+eps)-format med bevisade skalfel (100 000 "
            "för LUMI.ST, se DATATACKNING_48FEATURES_2026-08-07.md) — samma ekonomiska "
            "hypotes byggs här om från grunden med en robust formel.",
     ravalt=["Spår B R12: report_date (as-of)", "Spår A: adj"],
     formel="adj[T]/adj[vid report_date]-1", lookback="0–52v (varierar med "
           "fundamenta_days_since)", pit="report_date≤T garanterat av samma as-of-mekanism som "
           "övriga fundamentafält; prispunkten vid report_date tas ur Spår A, alltid ≤T",
     missing="null om has_fundamenta=False", survivorship="EJ säkert (ärver fundamentans "
            "begränsning)", redundans="medel mot mom_-familjen (delar prisserie) men mäter "
            "en specifikt händelseankrad period, inte ett fast kalenderfönster")
lägg(id="market_regime_trend", familj="EVENT/marknadsregim", status="NY_BYGGD",
     hypotes="Är marknaden i en upp- eller nedtrend? Kontext-feature, inte bolagsspecifik — "
            "låter en modell villkora bolagssignaler på regim.",
     ravalt=["egenbyggt index (adj-baserat)"], formel="index[T]/SMA(index,26v)-1", lookback="26v",
     pit="rullande fönster, endast data ≤T", missing="null vid <26v indexhistorik",
     survivorship="säkert", redundans="låg — samma värde för alla instrument samma panel_date, "
                 "en ren tidsserie-kontext")
lägg(id="market_regime_vol", familj="EVENT/volatilitetsregim", status="NY_BYGGD",
     hypotes="Hög eller låg marknadsvolatilitet — momentum är dokumenterat instabilt "
            "('momentum crashes') i högvolatila regimer.",
     ravalt=["egenbyggt index (adj-baserat)"], formel="std(indexets veckoavkastningar, 13v)",
     lookback="13v", pit="rullande fönster, endast data ≤T", missing="null vid <8v indexhistorik",
     survivorship="säkert", redundans="låg — marknadsnivå, inte bolagsnivå")
lägg(id="explicit_interaktionstermer", familj="EVENT/interaktioner", status="BOR_INTE_BYGGAS",
     hypotes="T.ex. momentum×volatilitetsregim (momentum-krascher är dokumenterat "
            "regimberoende).",
     ravalt=["samtliga ovanstående, i kombination"], formel="—", lookback="—",
     anmarkning="AVRÅDES i detta steg: att handplocka EN specifik interaktion i förväg är att "
                "göra ett implicit, odokumenterat antagande om vilken kombination som kommer "
                "vara prediktiv — precis den sortens beslut som riskerar att smyga in "
                "targetinformerad optimering genom bakvägen, vilket uppdraget uttryckligen "
                "förbjuder i detta steg. Trädbaserade modeller (LightGBM/CatBoost/XGBoost, "
                "redan planerade för modellracet) fångar interaktioner automatiskt från "
                "regressorerna var för sig — en handbyggd interaktionsterm tillför inget en "
                "sådan modell inte redan kan hitta själv, men LÅSER i förväg en hypotes om "
                "VILKEN interaktion som spelar roll.")

# ---------------------------- KONTEXT/PROVENANCE ------------------------------
lägg(id="has_fundamenta", familj="PROVENANCE", status="IMPLEMENTERAD",
     hypotes="Obligatorisk provenance-flagga, inte en alfakandidat.",
     ravalt=["Spår B R12-tillgänglighet"], formel="bool", lookback="—", pit="trivialt (samma "
            "as-of-mekanism)", missing="aldrig null", survivorship="—", redundans="—")
lägg(id="fundamenta_days_since", familj="PROVENANCE", status="IMPLEMENTERAD",
     hypotes="Rapportens ålder/färskhet, provenance snarare än alfa i sig — även om ålder på "
            "information HAR dokumenterad prediktiv kraft i litteraturen (informationsförfall), "
            "syftet här är spårbarhet.",
     ravalt=["Spår B R12: report_date"], formel="T - report_date", lookback="—",
     pit="trivialt", missing="null endast om has_fundamenta=False", survivorship="—", redundans="—")
lägg(id="sector_code_context", familj="PROVENANCE/klassificering", status="KAN_BYGGAS",
     hypotes="Kategorisk kontext (Börsdata sectorId), inte en numerisk alfakandidat i sig — "
            "kräver one-hot/embedding-hantering i en modell, inte en 'feature' i den mening "
            "övriga poster i denna blueprint är.",
     ravalt=["Börsdata sectorId (instruments_live.json, EJ PIT)"], formel="kategorisk kod",
     redundans="—", anmarkning="INTE byggd denna omgång — hanteras bäst som en explicit "
                "modellbeslut (one-hot/target-encoding) i en senare fas, inte som en "
            "panelkolumn i Spår C")

# ----------------------- B-EXTRA / FORMELL BEDÖMNING ----------------------
lägg(id="ebitda_margin_ttm", familj="FUNDAMENTA/lönsamhet",
     status="NY_BYGGD",
     hypotes="EBITDA relativt omsättning, före av- och nedskrivningar.",
     ravalt=["Spår B-extra R12: EBITDA value_sek", "Spår B R12: revenues"],
     formel="EBITDA/revenues med samma materialitetsgrind som övriga marginaler",
     lookback="0", pit="as-of report_date≤T", missing="null om KPI/rapport saknas",
     survivorship="EJ säkert", redundans="hög mot operating_margin_ttm",
     anmarkning="Byggd utan targetkontakt efter PIT-, valuta-, enhets-, coverage- och EBITDA-vs-EBIT-QA; samma materialitetsgrind som övriga marginaler")
lägg(id="capex_intensity_ttm", familj="FUNDAMENTA/investeringar",
     status="SAKNAR_DATA",
     hypotes="Investeringstakt relativt omsättning.",
     ravalt=["Spår B-extra R12: Capex value_sek", "Spår B R12: revenues"],
     formel="—", lookback="0", pit="as-of report_date≤T",
     missing="null", survivorship="EJ säkert", redundans="medel",
     anmarkning="BLOCKERAD: Capex har blandad teckensemantik (positiva, negativa och korrigerande värden); ingen generell cash-out-definition är QA-godkänd")
lägg(id="shareholder_yield_buyback", familj="FUNDAMENTA/kapitalallokering",
     status="SAKNAR_DATA", hypotes="Utdelning plus nettoåterköp relativt börsvärde.",
     ravalt=["buyback-transaktioner/KPI 213–215", "PIT-börsvärde"], formel="—",
     lookback="52v", pit="—", missing="hela dimensionen", survivorship="—",
     redundans="låg", anmarkning="BLOCKERAD: KPI 213–215 saknar fullskala och transaktioner saknar QA-godkänd FX/correction/cashflow samt verifierad denominator")
lägg(id="cap_tier_code_context", familj="PROVENANCE/klassificering", status="KAN_BYGGAS",
     hypotes="Storleksklass (Large/Mid/Small Cap), samma resonemang som sector_code_context.",
     ravalt=["Börsdata marketId (redan använt för att DEFINIERA universumet, EJ PIT-varierat "
            "över tid)"], formel="kategorisk kod", redundans="—",
     anmarkning="INTE byggd denna omgång, samma skäl som sector_code_context")

if __name__ == "__main__":
    # En enda aktuell statusvokabulär. Historiska IMPLEMENTERAD/NY_BYGGD
    # kollapsas till faktisk IMPLEMENTERAD; blockerade 0 %-kolumner får aldrig
    # räknas som användbar featurebas.
    status_map = {
        "NY_BYGGD": "IMPLEMENTERAD",
        "KAN_BYGGAS": "KAN BYGGAS MEN UPPSKJUTEN",
        "SAKNAR_DATA": "BLOCKERAD/SAKNAR DATA",
        "BOR_INTE_BYGGAS": "BÖR INTE BYGGAS",
    }
    blockerade = {"turnover_13w_msek", "illiquidity_amihud_13w",
                  "dividend_yield_ttm", "fcf_yield_ttm"}
    for f in BP:
        f["status"] = status_map.get(f["status"], f["status"])
        if f["id"] in blockerade:
            f["status"] = "BLOCKERAD/SAKNAR DATA"
            f["anmarkning"] = "0 % coverage; aktiv kod skriver null. Inte del av användbar featurebas."
    OUT.write_text(json.dumps(BP, indent=1, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    c = Counter(f["status"] for f in BP)
    print(f"BLUEPRINT: {len(BP)} kandidater")
    print(dict(c))
    print(f"artefakt: {OUT}")
