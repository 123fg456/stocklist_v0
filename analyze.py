"""KR stock flow prototype. Unofficial pykrx, no brokerage credentials."""
import argparse, json, math, os, re, time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parent
WINDOWS = [1, 3, 5, 10, 20, 60, 120]

def clean_name(name):
    return not bool(re.search(r'(스팩|SPAC|우$|우B$|우C$|우\(|ETF|ETN)', name, re.I))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=100, help='Maximum tickers to attempt; 0 means all')
    p.add_argument('--date', default='', help='YYYYMMDD, default most recent weekday')
    args=p.parse_args()
    now=datetime.now(ZoneInfo('Asia/Seoul'))
    d=datetime.strptime(args.date,'%Y%m%d').date() if args.date else now.date()
    if not args.date and now.hour < 20 and d.weekday() < 5:
        d-=timedelta(days=1)
    while d.weekday()>=5: d-=timedelta(days=1)
    end=d.strftime('%Y%m%d')
    start=(d-timedelta(days=245)).strftime('%Y%m%d')
    result={'run_at':now.isoformat(), 'requested_date':end, 'source':'pykrx (unofficial KRX web wrapper)', 'source_url':'https://github.com/sharebook-kr/pykrx', 'data_verified_live':False, 'status':'NOT_VERIFIED', 'universe_count':0,'attempted':0,'verified':0,'failures':[], 'rows':[]}
    try:
        universe={}
        for market in ['KOSPI','KOSDAQ']:
            tickers=stock.get_market_ticker_list(end, market=market)
            if not tickers: raise RuntimeError(f'{market} ticker list empty on {end}; data source unavailable or market holiday')
            for ticker in tickers:
                name=stock.get_market_ticker_name(ticker)
                if clean_name(name) and len(ticker)==6 and ticker.isdigit(): universe[ticker]=(name,market)
        result['universe_count']=len(universe)
        items=list(universe.items())
        if args.limit>0: items=items[:args.limit]
        for ticker,(name,market) in items:
            result['attempted']+=1
            try:
                df=stock.get_market_trading_value_by_date(start,end,ticker)
                prices=stock.get_market_ohlcv_by_date(start,end,ticker)
                if df is None or prices is None or df.empty or prices.empty: raise ValueError('empty response')
                df.index=pd.to_datetime(df.index); prices.index=pd.to_datetime(prices.index)
                cols=['외국인합계','기관합계']
                if not all(c in df.columns for c in cols): raise ValueError('missing investor columns')
                if '거래대금' not in prices.columns or '종가' not in prices.columns: raise ValueError('missing price columns')
                joined=df[cols].join(prices[['종가','거래대금']],how='inner').sort_index()
                joined=joined.loc[joined.index<=pd.Timestamp(d)]
                joined=joined[(joined['종가']>0)&(joined['거래대금']>0)]
                if len(joined)<120: raise ValueError(f'only {len(joined)} matching trading dates (<120)')
                if joined.index[-1].strftime('%Y%m%d')!=end: raise ValueError('latest matched date is not requested date')
                data={}
                for w in WINDOWS:
                    a=joined.tail(w)
                    turnover=float(a['거래대금'].sum())
                    if turnover<=0: raise ValueError('invalid turnover')
                    data[str(w)]={'foreign_krw':int(a['외국인합계'].sum()),'institution_krw':int(a['기관합계'].sum()),'turnover_krw':int(turnover), 'foreign_positive_days':int((a['외국인합계']>0).sum()),'institution_positive_days':int((a['기관합계']>0).sum())}
                f=data['20']['foreign_krw']/data['20']['turnover_krw']
                i=data['20']['institution_krw']/data['20']['turnover_krw']
                # Transparent, fixed descriptive ranking score; NOT a validated predictive model.
                score=round(35*max(0,min(1,f/.08))+30*max(0,min(1,i/.08))+15*(data['20']['foreign_positive_days']/20)+20*(data['20']['institution_positive_days']/20),2)
                result['rows'].append({'ticker':ticker,'name':name,'market':market,'date':end,'close_krw':int(joined['종가'].iloc[-1]),'score_flow_only_100':score,'windows':data})
                result['verified']+=1
            except Exception as exc:
                result['failures'].append({'ticker':ticker,'reason':str(exc)[:180]})
            time.sleep(.15)
        result['rows'].sort(key=lambda x:x['score_flow_only_100'],reverse=True)
        result['status']='PARTIAL_VERIFIED' if result['verified'] else 'NO_VERIFIED_DATA'
        result['data_verified_live']=bool(result['verified'])
    except Exception as exc:
        result['failures'].append({'stage':'universe','reason':str(exc)[:300]})
        result['status']='FAILED'
    ROOT.joinpath('report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','universe_count','attempted','verified']},ensure_ascii=False))
    if result['verified']==0: raise SystemExit(2)

if __name__=='__main__': main()
