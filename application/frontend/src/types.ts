export type Evidence={label:string;value:unknown};
export type BusinessCase={id:string;title:string;owner:string;severity:string;status:string;exposureCents:number;impactLabel:string;description:string;evidence:Evidence[];recommendation:string;departments:string[];affectedOrderIds:number[]};
export type Workflow={version:number;status:string;plan:unknown;assignment:unknown};
export type Role={id:string;name:string;recordCount:number;focus:string};
export type Bootstrap={company:string;asOf:string;synthetic:boolean;roles:Role[];cases:BusinessCase[];metrics:Record<string,number>;departmentMetrics:Record<string,number>;counts:Record<string,number>;monthly:{month:string;recognizedRevenueCents:number}[];network:{id:number;name:string;country:string;region:string}[];assumptions:string[]|Record<string,unknown>;workflow:{run_id:string;cases:Record<string,Workflow>}};
export type CaseDetail=BusinessCase&{workflow:Workflow;evidenceRows:Record<string,unknown>[];run_id?:string};
