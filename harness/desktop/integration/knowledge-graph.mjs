// One bounded physical model for initial placement and direct manipulation.
export function stepForces(nodes,edges){
  const byId=new Map(nodes.map(n=>[n.id,n])),forces=nodes.map(()=>({x:0,y:0}));
  nodes.forEach((a,i)=>{for(let j=i+1;j<nodes.length;j++){
    const b=nodes[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy;
    if(d2<1){dx=Math.cos(i*2.4+j);dy=Math.sin(i*2.4+j);d2=1;}
    const d=Math.sqrt(d2),strength=Math.min(5,2400/Math.max(100,d2));
    forces[i].x+=dx/d*strength;forces[i].y+=dy/d*strength;
    forces[j].x-=dx/d*strength;forces[j].y-=dy/d*strength;
    if(a.labelWidth&&b.labelWidth&&Math.abs(dx)<(a.labelWidth+b.labelWidth)/2+12&&Math.abs(dy)<34){
      const separation=(34-Math.abs(dy))*.055*(dy<0?-1:1);
      forces[i].y+=separation;forces[j].y-=separation;
    }
  }});
  const indices=new Map(nodes.map((n,i)=>[n.id,i]));
  for(const e of edges){const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),force=(d-(e.length||145))*.012;
    const x=dx/d*force,y=dy/d*force;forces[indices.get(a.id)].x+=x;forces[indices.get(a.id)].y+=y;forces[indices.get(b.id)].x-=x;forces[indices.get(b.id)].y-=y;
  }
  let movement=0;
  nodes.forEach((n,i)=>{if(n.fixed){n.vx=n.vy=0;return;}
    n.vx=((n.vx||0)+forces[i].x-n.x*.001)*.82;n.vy=((n.vy||0)+forces[i].y-n.y*.001)*.82;
    const speed=Math.hypot(n.vx,n.vy);if(speed>10){n.vx*=10/speed;n.vy*=10/speed;}
    n.x+=n.vx;n.y+=n.vy;movement=Math.max(movement,Math.hypot(n.vx,n.vy));
  });return movement;
}

export function createKnowledgeGraph({factory,container,elements,cache=new Map(),onChoose,paused=false}){
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const nodes=elements.filter(e=>!e.data.source).map((e,i)=>{
    const p=cache.get(e.data.id)||{x:Math.cos(i*2.399)*Math.sqrt(i)*70,y:Math.sin(i*2.399)*Math.sqrt(i)*70};
    return {id:e.data.id,...p,labelWidth:Math.min(130,String(e.data.label||'').length*11),vx:0,vy:0,fixed:false};
  }),edges=elements.filter(e=>e.data.source).map(e=>e.data),byId=new Map(nodes.map(n=>[n.id,n]));
  if(!nodes.some(n=>cache.has(n.id)))for(let i=0;i<180;i++)stepForces(nodes,edges);
  const cy=factory({container,elements:elements.map(e=>byId.has(e.data.id)?{...e,position:{x:byId.get(e.data.id).x,y:byId.get(e.data.id).y}}:e),layout:{name:'preset',fit:false},minZoom:.25,maxZoom:2.5,wheelSensitivity:.2,style:[
    {selector:'node',style:{label:'data(label)',width:12,height:12,'background-color':'#738293',color:'#364353','font-size':11,'font-family':'Microsoft YaHei, sans-serif','text-valign':'bottom','text-margin-y':9,'text-wrap':'ellipsis','text-max-width':130,'text-background-color':'#f8fafc','text-background-opacity':.9,'text-background-padding':3,'overlay-opacity':0}},
    {selector:'node[kind="project"]',style:{width:25,height:25,'background-color':'#325f80','font-size':14,'font-weight':600}},
    {selector:'node[kind="source"]',style:{width:18,height:18,'background-color':'#47846e'}},
    {selector:'node[kind="rule"],node[kind="preference"]',style:{'background-color':'#b0803e'}},
    {selector:'node[kind="case_memory"]',style:{'background-color':'#79659b',width:15,height:15}},
    {selector:'node[kind="resource"]',style:{'background-color':'#47846e','shape':'round-rectangle',width:16,height:16}},
    {selector:'edge',style:{width:.85,'line-color':'#aab6c2',opacity:.5,'curve-style':'straight','overlay-opacity':0}},
    {selector:'edge[candidate = true]',style:{'line-style':'dashed',opacity:.35}},
    {selector:'.dim',style:{opacity:.14,'text-opacity':.1}},
    {selector:'.near',style:{opacity:1,'line-color':'#54758e',width:1.5}},
    {selector:'node:selected',style:{'border-width':3,'border-color':'#325f80','border-opacity':.4,'background-color':'#325f80'}},
  ]});
  const view=cache.get('__viewport');if(view)cy.viewport(view);else{cy.fit(undefined,55);if(cy.zoom()>1.15){cy.zoom(1.15);cy.center();}}
  let frame=0,steps=0,quiet=0,disposed=false,dragging=false,visible=true;
  function save(){if(!nodes.length)return;cy.nodes().forEach(n=>cache.set(n.id(),{...n.position()}));cache.set('__viewport',{zoom:cy.zoom(),pan:{...cy.pan()}});}
  function paint(){cy.batch(()=>nodes.forEach(n=>{if(!n.fixed)cy.getElementById(n.id).position({x:n.x,y:n.y});}));}
  function stop(){cancelAnimationFrame(frame);frame=0;}
  function tick(){frame=0;if(disposed||paused||media.matches||document.hidden||!visible)return;
    const movement=stepForces(nodes,edges);paint();quiet=movement<.025?quiet+1:0;
    if((quiet<25&&steps++<900)||dragging)frame=requestAnimationFrame(tick);else save();
  }
  function wake(){steps=quiet=0;if(!frame&&!paused&&!media.matches&&!document.hidden&&visible&&!disposed)frame=requestAnimationFrame(tick);}
  function highlight(node){cy.elements().removeClass('dim near');if(node){const near=node.closedNeighborhood();cy.elements().not(near).addClass('dim');near.edges().addClass('near');}}
  cy.on('grab','node',e=>{const n=byId.get(e.target.id());n.fixed=true;n.vx=n.vy=0;dragging=true;highlight(e.target);wake();});
  cy.on('drag','node',e=>{const n=byId.get(e.target.id());Object.assign(n,e.target.position());wake();});
  cy.on('free','node',e=>{const n=byId.get(e.target.id());Object.assign(n,e.target.position());n.fixed=false;dragging=false;save();wake();});
  cy.on('mouseover','node',e=>highlight(e.target));cy.on('mouseout','node',()=>{if(!dragging)highlight(cy.$('node:selected')[0]);});
  cy.on('tap',e=>{if(e.target===cy){cy.elements().unselect();highlight(null);return;}if(e.target.isNode()){highlight(e.target);onChoose?.(e.target.data());}});
  cy.on('zoom',()=>{const zoom=cy.zoom();cy.style().selector('node').style({'font-size':Math.min(18,11/zoom),'text-opacity':zoom<.42?0:1}).update();save();});
  cy.on('pan',save);
  const visibility=()=>document.hidden?stop():wake();document.addEventListener('visibilitychange',visibility);
  const preference=()=>{stop();if(!media.matches)wake();};media.addEventListener('change',preference);
  const resize=new ResizeObserver(()=>cy.resize());resize.observe(container);wake();
  const intersection=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible)wake();else stop();});intersection.observe(container);
  return {cy,setPaused(value){paused=value;stop();if(!paused)wake();},reset(){cache.delete('__viewport');nodes.forEach((n,i)=>{n.x=Math.cos(i*2.399)*Math.sqrt(i)*70;n.y=Math.sin(i*2.399)*Math.sqrt(i)*70;n.vx=n.vy=0;});for(let i=0;i<180;i++)stepForces(nodes,edges);paint();cy.fit(undefined,55);save();wake();},destroy(){if(disposed)return;save();disposed=true;stop();resize.disconnect();intersection.disconnect();document.removeEventListener('visibilitychange',visibility);media.removeEventListener('change',preference);cy.destroy();}};
}
