/* ERRORS M564: a saved indicator list from before the registry held the reference's one moving average ('ma', saved as
   'ema' when its type was EMA) with a type switch in its params (type, length, source, offset) and one flat style
   {color, width}. Today 'ema' is the registry's EMA (I02): params {length, source}, and its style kept per output
   (style.out.ema) with the offset beside it. The migration took every 'ema' for the old one, so today's EMA lost its
   colour, width and offset on every load (and, since the timeframe is built in place, on every switch): its saved
   style became {out:{ema:{color:undefined, width:undefined}}}.
   Which form an entry is in is read from its shape: today's style keeps its colours under `out`, the old one did not,
   and only the old one had a type among its params or a colour, a width at the top of its style, or an offset among
   its params. The ids name which indicator the old form was ('ma' is no definition today, so it is always the old
   form); they no longer decide the form. */

type Saved = { def: string; on?: boolean; params?: Record<string, any>; style?: Record<string, any>; [k: string]: any };
const OLD_MA = ['ma', 'ema'];
const isObj = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v);

/** a saved entry in the pre-registry moving average's form */
export function isPreRegistryMa(o: Saved): boolean {
  if (!OLD_MA.includes(o.def)) return false;
  const st = o.style, pa = isObj(o.params) ? o.params : {};
  if (isObj(st) && isObj(st.out)) return false;              // today's form: colours per output
  return o.def === 'ma' || typeof pa.type === 'string' || pa.offset !== undefined || (isObj(st) && ('color' in st || 'width' in st));
}

/** the pre-registry moving average as today's registry entry of its type (SMA, EMA, ...); every other entry unchanged */
export function migrateSaved<T extends Saved>(o: T): T | Saved {
  if (!isPreRegistryMa(o)) return o;
  const pa = isObj(o.params) ? o.params : {}, st = isObj(o.style) ? o.style : {};
  const key = String(pa.type || (o.def === 'ema' ? 'EMA' : 'SMA')).toLowerCase();
  // only what the entry holds: a colour or width it lacks takes the indicator's default (not undefined over it)
  const look = Object.fromEntries((['color', 'width'] as const).filter(k => st[k] !== undefined).map(k => [k, st[k]]));
  return { def:key, on:o.on, params:{ length:pa.length, source:String(pa.source || 'close').toLowerCase() },
    style:{ out:{ [key]:look }, offset:pa.offset || 0 } };
}
