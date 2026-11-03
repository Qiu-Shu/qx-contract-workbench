import {realpath, stat} from 'node:fs/promises';
import {isAbsolute, relative, sep} from 'node:path';

export function ownerAccepts(account, message) {
  if (!account?.userId || message?.message_type === 2) return false;
  if (message?.group_id || message?.room_id || message?.chat_room_id || String(message?.session_id ?? '').includes('@chatroom')) return false;
  return message?.from_user_id === account.userId;
}

export async function workspaceFile(workspace, path) {
  const [base, target] = await Promise.all([realpath(workspace), realpath(path)]);
  const rel = relative(base, target);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) throw new Error('只能发送当前工作区内的文件');
  if (!(await stat(target)).isFile()) throw new Error('发送路径必须是文件');
  return target;
}

export function publicLogin(session) {
  if (!session) return null;
  return {id:session.id,status:session.status,message:session.message,error:session.error,
    verifyCodeNeeded:Boolean(session.verifyCodeNeeded),qrPayload:session.qrPayload,
    userId:session.userId,accountId:session.accountId};
}
