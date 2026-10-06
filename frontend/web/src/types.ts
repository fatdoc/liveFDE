export type AssetStatus = 'pending' | 'approved' | 'rejected' | 'withdrawn'
export type Session = {id:string;title:string;host:string;date:string;platform:string;duration:string;status:'review'|'complete'|'prepared'|'draft';material?:string}
export type Asset = {id:string;sessionId:string;quote:string;category:string;host:string;date:string;time:string;seconds:number;why:string;condition:string;caution:string;adapted:string;status:AssetStatus;favorite:boolean;learned:boolean;adopted:boolean;reviewNote?:string}
export type Section = {id:string;title:string;minutes:number;goal:string;html:string;prompt:string;assetIds:string[]}
export type Plan = {id:string;title:string;host:string;date:string;status:'draft'|'ready';sections:Section[]}
export type ReportDraft = {summary:string;strengths:string;issues:string;actions:string;owner:string;check:string;visible:string[];version:number;confirmed:boolean;sourceSignature?:string}
export type State = {sessions:Session[];assets:Asset[];plans:Plan[];workspace:string;weeklyNotes:string;reportDrafts:Record<string,ReportDraft>}
export const categories=['全部','开场留人','用户痛点','互动引导','案例信任','产品承接','成交推动']
