import { SQL } from "bun";

// One-off universe enrollment. Source metadata must resolve successfully first.
const response = await fetch("https://scanner.tradingview.com/indonesia/scan", {
  method: "POST", headers: {"Content-Type":"application/json"},
  body: JSON.stringify({symbols:{tickers:["IDX:COMPOSITE"]},columns:["name","description","type","typespecs","currency","isin","country","sector","industry"]}),
  signal: AbortSignal.timeout(30000)
});
if (!response.ok) throw new Error(`Metadata HTTP ${response.status}`);
const payload = await response.json() as any;
if (payload.totalCount !== 1 || payload.data?.length !== 1) throw new Error("Expected exactly one provider symbol");
const item = payload.data[0];
console.log("IHSG_PROVIDER_RAW::"+JSON.stringify(item));
const [name,description,type,typespecs,currency,isin,country,sector,industry] = item.d;
if(item.s!=="IDX:COMPOSITE" || name!=="COMPOSITE" || type!=="index") throw new Error("Provider symbol/type mismatch");
const specValues=Array.isArray(typespecs)?typespecs.filter((v:any)=>typeof v==="string" && v.trim()):[];
const specs=specValues.length?specValues.join(","):"Undefined";
const row = {
  "Region":"Asia", "Country":"Indonesia", "Company Name":description,
  "Ticker":"IHSG", "Exchange":"IDX", "TradingView Symbol":item.s,
  "TradingView URL":"https://www.tradingview.com/symbols/IDX-COMPOSITE/",
  "Security Type":type,"Type Specs":specs,"Is Common Stock":"No",
  "TradingView Country":country||"Indonesia","Currency":currency||"Not applicable",
  "Fundamental Currency":"Not applicable","ISIN":isin||"Not applicable",
  "Sector":sector||"Undefined","Industry":industry||"Undefined"
};
console.log("IHSG_PROVIDER_METADATA::"+JSON.stringify({provider:item.s,row}));
if(Bun.env.ACTION!=="apply") {
 console.log("IHSG_PREFLIGHT_ONLY::No database changes");
} else {
 if(!Bun.env.DATABASE_URL) throw new Error("Database URL missing");
 const db=new SQL(Bun.env.DATABASE_URL);
 try {
  const result=await db.begin(async tx=>{
   await tx`SET LOCAL lock_timeout='5s'`;
   await tx`SET LOCAL statement_timeout='30s'`;
   await tx`SELECT pg_advisory_xact_lock(hashtextextended('universe-enrollment:IDX:COMPOSITE',0))`;
   const existing=await tx`SELECT * FROM public."IDX_Stock_Universe" WHERE "Ticker"=${row.Ticker} OR "TradingView Symbol"=${item.s}`;
   if(existing.length){
    if(existing.length!==1 || existing[0]["Ticker"]!==row.Ticker || existing[0]["TradingView Symbol"]!==item.s || existing[0]["Security Type"]!=="index") throw new Error("Existing identity conflict; no row overwritten");
    return {inserted:0,row:existing[0]};
   }
   const inserted=await tx`INSERT INTO public."IDX_Stock_Universe" ("Region","Country","Company Name","Ticker","Exchange","TradingView Symbol","TradingView URL","Security Type","Type Specs","Is Common Stock","TradingView Country","Currency","Fundamental Currency","ISIN","Sector","Industry") VALUES (${row.Region},${row.Country},${row["Company Name"]},${row.Ticker},${row.Exchange},${row["TradingView Symbol"]},${row["TradingView URL"]},${row["Security Type"]},${row["Type Specs"]},${row["Is Common Stock"]},${row["TradingView Country"]},${row.Currency},${row["Fundamental Currency"]},${row.ISIN},${row.Sector},${row.Industry}) RETURNING *`;
   if(inserted.length!==1)throw new Error("Expected one inserted row");
   return {inserted:1,row:inserted[0]};
  });
  console.log("IHSG_UNIVERSE_COMMITTED::"+JSON.stringify(result));
 } finally {await db.close();}
}
