/* Shared keyboard, navigation and dialog behavior. No decorative motion on keyboard input. */
(() => {
  const nav=document.getElementById('appNavigation');
  const toggle=document.getElementById('mobileNavToggle');
  const scrim=document.getElementById('navScrim');
  const smallScreen=matchMedia('(max-width:820px)');
  const syncNav=()=>{if(nav){nav.inert=smallScreen.matches&&!nav.classList.contains('open');nav.setAttribute('aria-hidden',String(nav.inert))}};
  smallScreen.addEventListener('change',syncNav);syncNav();
  const setNav=open=>{if(!nav)return;const wasOpen=nav.classList.contains('open');nav.classList.toggle('open',open);scrim.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'Fechar navegação':'Abrir navegação');syncNav();if(open)nav.querySelector('button.active')?.focus();else if(wasOpen)toggle.focus()};
  toggle?.addEventListener('click',()=>setNav(!nav.classList.contains('open')));
  scrim?.addEventListener('click',()=>{setNav(false);toggle.focus()});
  document.addEventListener('fintrack:navigate',e=>{setNav(false);document.querySelectorAll('.nav button').forEach(button=>{if(button.dataset.page===e.detail)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current')});window.scrollTo({top:0,behavior:'instant'})});
  document.querySelectorAll('.field').forEach(field=>{const label=field.querySelector('label');const input=field.querySelector('input:not([type=hidden]),select,textarea');if(label&&input?.id&&!label.htmlFor)label.htmlFor=input.id});
  document.querySelectorAll('.status').forEach(s=>s.setAttribute('role','status'));
  document.getElementById('toast')?.setAttribute('role','status');
  document.addEventListener('keydown',e=>{document.documentElement.classList.add('keyboard-input');if(e.key==='Escape'&&nav?.classList.contains('open')){setNav(false);toggle.focus()}});
  document.addEventListener('pointerdown',()=>document.documentElement.classList.remove('keyboard-input'));
  const focusables=el=>[...el.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled):not([type=hidden]),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(x=>x.getClientRects().length);
  const modalState=new WeakMap();
  function prepareModal(modal){
    if(modalState.has(modal))return;
    const dialog=modal.querySelector('.dialog');if(!dialog)return;
    const heading=dialog.querySelector('h2');if(heading&&!heading.id)heading.id=modal.id+'-heading';
    dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');if(heading)dialog.setAttribute('aria-labelledby',heading.id);
    dialog.tabIndex=-1;modalState.set(modal,{open:false,trigger:null});
    const sync=()=>{const state=modalState.get(modal);const open=modal.classList.contains('open');if(open===state.open)return;state.open=open;modal.setAttribute('aria-hidden',String(!open));if(open){state.trigger=document.activeElement;document.body.style.overflow='hidden';document.querySelector('.shell')?.setAttribute('inert','');document.getElementById('mascot')?.setAttribute('inert','');const first=focusables(dialog).find(x=>x.matches('input,select,textarea'))||focusables(dialog)[0]||dialog;first.focus()}else{if(!document.querySelector('.modal.open')){document.body.style.overflow='';document.querySelector('.shell')?.removeAttribute('inert');document.getElementById('mascot')?.removeAttribute('inert');}if(state.trigger?.isConnected)state.trigger.focus()}};
    new MutationObserver(sync).observe(modal,{attributes:true,attributeFilter:['class']});sync();
    modal.addEventListener('keydown',e=>{if(e.key==='Tab'){const items=focusables(dialog);if(!items.length){e.preventDefault();dialog.focus();return}const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();const close=dialog.querySelector('[data-close]');if(close)close.click();else if(typeof attemptClose==='function')attemptClose(modal.id)}});
  }
  document.querySelectorAll('.modal').forEach(prepareModal);
  new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1){if(node.matches('.modal'))prepareModal(node);node.querySelectorAll('.modal').forEach(prepareModal)}}))).observe(document.body,{childList:true,subtree:true});
})();
