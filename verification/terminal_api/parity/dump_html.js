const TA = require('./ta_engine.js'); const d = require('./data.json').BBCA; const P = d.price;
const B = { T:P.map(r=>r[0]), O:P.map(r=>r[1]), H:P.map(r=>r[2]), L:P.map(r=>r[3]), C:P.map(r=>r[4]), V:P.map(r=>r[5]) };
const runs = {
  wma:['wma',{source:'close',length:20},'wma'], kama:['kama',{source:'close',length:10,fast_length:2,slow_length:30},'kama'],
  aroon_up:['aroon',{length:14},'aroon_up'], aroon_down:['aroon',{length:14},'aroon_down'],
  sar:['psar',{start:0.02,increment:0.02,maximum:0.2},'sar'],
  stochrsi_k:['stoch_rsi',{source:'close',rsi_length:14,stoch_length:14,smooth_k:3,smooth_d:3},'k'],
  stoch_k:['stochastic',{k_length:14,smooth_k:3,d_length:3},'k'], stoch_d:['stochastic',{k_length:14,smooth_k:3,d_length:3},'d'],
  willr:['williams_r',{source:'close',length:14},'williams_r'], roc:['roc',{source:'close',length:9},'roc'],
  mom:['momentum',{source:'close',length:10},'momentum'], cci:['cci',{length:20,constant:0.015},'cci'],
  cmo:['cmo',{source:'close',length:14},'cmo'], trix:['trix',{source:'close',length:15},'trix'],
  ultosc:['ultimate_osc',{fast_length:7,middle_length:14,slow_length:28,weight_fast:4,weight_middle:2,weight_slow:1},'uo'],
  ppo:['ppo',{source:'close',fast_length:12,slow_length:26,signal_length:9},'ppo'], bop:['bop',{},'bop'],
  natr:['natr',{length:14,smoothing_type:'RMA'},'natr'], stddev:['stddev',{source:'close',length:20,stdev_method:'population'},'stddev'],
  obv:['obv',{},'obv'], ad:['adl',{},'adl'], adosc:['chaikin_osc',{fast_length:3,slow_length:10},'chaikin_osc'],
  mfi:['mfi',{length:14},'mfi'], dc_upper:['donchian',{length:20},'upper'],
  plus_di:['adx',{di_length:14,adx_smoothing:14},'plus_di'],
};
const out = {T:B.T}; for (const [k,[fn,p,o]] of Object.entries(runs)) out[k] = TA.F[fn](B,p)[o];
require('fs').writeFileSync('html_out.json', JSON.stringify(out));
