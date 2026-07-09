// 02-transformation/tap.ts
// Side effect (log, debug)
//
// pnpm exec ts-node 02-transformation\tap.ts

import { of, tap } from "rxjs";

of('A', 'B').pipe(tap(v => { console.log('Tap:', v); })).subscribe();
