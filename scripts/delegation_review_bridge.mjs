// Local-only stdin/stdout bridge. No files, requests or persistent draft storage.
import {compareInputs} from '../web/delegation.mjs';
let input='';
try{
 for await(const chunk of process.stdin){input+=chunk;if(input.length>1000000)throw Error('입력 조문이 너무 깁니다.');}
 const {before,after,options}=JSON.parse(input);
 console.log(JSON.stringify({ok:true,result:compareInputs(before,after,options)}));
}catch(error){console.log(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;}
