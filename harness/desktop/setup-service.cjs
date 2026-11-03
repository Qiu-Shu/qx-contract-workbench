async function validateKey(value, request=fetch){
  const key=typeof value==='string'?value.trim():'';
  if(key.length<16||key.length>512||!/^[\x21-\x7e]+$/.test(key))return {ok:false,message:'请填写完整的 DeepSeek API Key。'};
  try{
    const response=await request('https://api.deepseek.com/user/balance',{
      headers:{Authorization:`Bearer ${key}`},redirect:'error',signal:AbortSignal.timeout(20000),
    });
    if(!response.ok)return {ok:false,message:response.status===401||response.status===403
      ?'API Key 未通过验证，请检查是否复制完整，或重新创建。':'DeepSeek 暂时无法验证，请稍后重试。'};
    const body=await response.json();
    if(typeof body.is_available!=='boolean'||!Array.isArray(body.balance_infos))return {ok:false,message:'DeepSeek 返回异常，请稍后重试。'};
    return {ok:true,available:body.is_available};
  }catch{return {ok:false,message:'暂时无法连接 DeepSeek，请检查网络后重试。'};}
}
module.exports={validateKey};
