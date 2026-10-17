/* TRV Scheduler 0.3.1 — bundled, dependency-free HA custom card. */
(() => {
  if (customElements.get('trv-scheduler-card')) return;
  const icon = name => {
    const paths = {
      clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
      locked: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="M12 14v3"/>',
      unlocked: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.5-2"/><path d="M12 14v3"/>',
      trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
  };
  class TRVSchedulerCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: 'open'});
      this._busy = false;
      this._canEdit = false;
      this._dirty = false;
      this._generation = 0;
    }
    setConfig(config) {
      if (!config.entity?.startsWith('climate.')) throw new Error('Bitte eine climate-Entität angeben.');
      this._config = config;
      if (!this._built) this._build();
    }
    set hass(value) { this._hass = value; }
    getCardSize() { return 1; }
    getGridOptions() { return {rows: 1, columns: 12}; }
    static getStubConfig(hass) {
      return {entity: Object.keys(hass.states).find(k => k.startsWith('climate.')) || 'climate.thermostat'};
    }
    disconnectedCallback() { clearInterval(this._poll); this._generation++; }
    _useWheels() { return matchMedia('(max-width: 600px), (any-pointer: coarse)').matches; }
    _build() {
      this._built = true;
      this.shadowRoot.innerHTML = `
        <style>
          :host {display:block; color:var(--primary-text-color,#18242d); font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
          * {box-sizing:border-box} button,input {font:inherit} button {cursor:pointer; touch-action:manipulation}
          svg {width:20px;height:20px;vertical-align:middle;flex-shrink:0} .help svg {width:15px;height:15px}
          button:focus-visible,input:focus-visible {outline:3px solid var(--primary-color,#0288d1);outline-offset:2px}
          button:disabled,input:disabled {opacity:.5;cursor:default}
          .launcher {display:flex;gap:10px;align-items:center;justify-content:center;width:100%;min-height:48px;border:0;background:transparent;color:var(--primary-color,#0288d1);font-weight:600;border-radius:12px}
          dialog {color:inherit;background:var(--card-background-color,#fff);border:0;border-radius:20px;padding:20px;width:min(520px,calc(100vw - 24px));max-height:calc(100dvh - 32px);overflow:auto;box-shadow:0 16px 70px #0005}
          dialog::backdrop {background:#0007}
          header {display:flex;align-items:start;justify-content:space-between;gap:12px}
          h2 {margin:0;font-size:21px;font-weight:650;line-height:1.25}
          .subtitle {font-size:13px;color:var(--secondary-text-color,#65717b);margin:5px 0 18px}
          .icon {border:0;border-radius:10px;background:transparent;color:inherit;min-height:40px;min-width:40px;padding:4px;font-size:19px}
          .icon:hover {background:var(--secondary-background-color,#f1f4f6)}
          .plan {display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-top:1px solid var(--divider-color,#e5e9ec)}
          .plan strong {font-size:15px} .switch {border:0;background:#74818a;border-radius:16px;min-width:42px;height:26px;padding:3px;display:inline-flex;align-items:center;justify-content:flex-start}
          .switch[aria-checked=true] {background:var(--primary-color,#0288d1);justify-content:flex-end}
          .switch span {width:20px;height:20px;background:white;border-radius:50%;box-shadow:0 1px 3px #0003}
          table {width:100%;border-collapse:collapse;table-layout:fixed;margin-top:12px}
          th {font-weight:500;font-size:12px;color:var(--secondary-text-color,#65717b);text-align:left;padding:8px 2px}
          td {padding:8px 2px;border-top:1px solid var(--divider-color,#e5e9ec);text-align:center}
          th:nth-child(n+3) {text-align:center} col:nth-child(1) {width:27%} col:nth-child(2) {width:25%} col:nth-child(n+3) {width:16%}
          input {width:100%;min-width:0;height:42px;border:1px solid var(--divider-color,#dce2e6);border-radius:9px;background:var(--secondary-background-color,#f5f7f8);color:inherit;padding:5px;font-size:16px}
          tr.paused input {opacity:.6} .lock[aria-pressed=true] {background:var(--primary-color,#0288d1);color:white}
          input[readonly] {cursor:pointer;caret-color:transparent}
          input[aria-expanded=true] {border-color:var(--primary-color,#0288d1);box-shadow:0 0 0 1px var(--primary-color,#0288d1)}
          .picker-row td {padding:0 0 12px;border-top:0;text-align:left}
          .picker {padding:14px 10px 10px;border:1px solid var(--divider-color,#dce2e6);border-radius:14px;background:var(--card-background-color,#fff)}
          .picker-title {margin:0 0 12px;font-size:14px;font-weight:600;text-align:center}
          .wheel-labels {display:flex;gap:20px;text-align:center;color:var(--secondary-text-color,#65717b);font-size:12px}
          .wheel-labels span {flex:1}
          .wheel-stage {display:flex;position:relative;isolation:isolate;margin:4px 0 8px}
          .wheel-stage::before {content:'';position:absolute;top:88px;left:0;right:0;height:44px;border-radius:10px;background:var(--secondary-background-color,#edf2f5);z-index:-1}
          .wheel {height:220px;flex:1;min-width:0;overflow-y:auto;padding:88px 0;scroll-snap-type:y mandatory;scroll-padding-block:88px;overscroll-behavior-y:contain;touch-action:pan-y;scrollbar-width:none;-webkit-overflow-scrolling:touch;outline-offset:-3px;user-select:none;-webkit-user-select:none;mask-image:linear-gradient(to bottom,transparent,rgba(0,0,0,.25) 15%,#000 42%,#000 58%,rgba(0,0,0,.25) 85%,transparent);-webkit-mask-image:linear-gradient(to bottom,transparent,rgba(0,0,0,.25) 15%,#000 42%,#000 58%,rgba(0,0,0,.25) 85%,transparent)}
          .wheel::-webkit-scrollbar {display:none}
          .wheel:focus-visible {outline:2px solid var(--primary-color,#0288d1);border-radius:10px}
          .wheel-value {height:44px;display:flex;align-items:center;justify-content:center;scroll-snap-align:center;font-size:27px;line-height:1;font-variant-numeric:tabular-nums;letter-spacing:.02em}
          .wheel-value.selected {font-weight:650;color:var(--primary-color,#0288d1)}
          .wheel-colon {align-self:center;width:20px;text-align:center;font-size:26px;font-weight:600}
          .picker-actions {display:flex;gap:12px;justify-content:space-between;border-top:1px solid var(--divider-color,#e5e9ec);padding-top:8px}
          .picker-actions button {min-height:44px;flex:1;font-size:14px}
          .picker-apply {border:0;border-radius:10px;background:var(--primary-color,#0288d1);color:var(--text-primary-color,#fff);font-weight:600}
          .delete {color:var(--error-color,#ba3e3e)} .empty {padding:24px 0;color:var(--secondary-text-color,#65717b);font-size:14px;text-align:center}
          .add {width:100%;border:1px dashed var(--divider-color,#c9d4dd);background:transparent;color:var(--primary-color,#0288d1);min-height:44px;border-radius:10px;margin:12px 0;font-weight:600}
          .device {border-top:1px solid var(--divider-color,#e5e9ec);padding-top:14px;margin-top:6px;font-size:13px}
          .device p {margin:0 0 8px} .text-button {border:0;background:transparent;color:var(--primary-color,#0288d1);min-height:40px;padding:4px 8px;border-radius:8px}
          .help {font-size:12px;line-height:1.5;color:var(--secondary-text-color,#65717b);margin:10px 0 0}
          .message {font-size:13px;line-height:1.5;margin-top:12px;min-height:20px}
          .message.error {color:var(--error-color,#ba3e3e)} .footer {display:flex;justify-content:space-between;align-items:center;gap:8px}
          .save-state {font-size:12px;color:var(--secondary-text-color,#65717b)}
          [hidden] {display:none!important} .sr-only {position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
          @media(max-width:380px) {dialog {padding:12px} .icon {min-width:34px} h2 {font-size:19px} input {padding:3px}}
        </style>
        <ha-card><button class="launcher" aria-haspopup="dialog">${icon("clock")} Zeitsteuerung</button></ha-card>
        <dialog aria-labelledby="title">
          <header><div><h2 id="title">Zeitsteuerung</h2><p class="subtitle"></p></div><button class="icon close" aria-label="Dialog schließen">✕</button></header>
          <div class="plan"><strong>Täglicher Zeitplan</strong><button class="switch plan-toggle" role="switch" aria-label="Zeitplan aktivieren" aria-checked="false"><span></span></button></div>
          <table><colgroup><col><col><col><col><col></colgroup><thead><tr><th>Uhrzeit</th><th>Soll <span class="unit">°C</span></th><th>Aktiv</th><th>Sperre</th><th><span class="sr-only">Löschen</span></th></tr></thead><tbody></tbody></table>
          <div class="empty">Noch keine Schaltzeiten. Mit ＋ hinzufügen.</div>
          <button class="add">＋ Schaltzeit hinzufügen</button>
          <p class="help">${icon("locked")} sperrt den Drehring ab dieser Uhrzeit. ${icon("unlocked")} gibt ihn frei. Der Zustand gilt bis zum nächsten aktiven Schaltpunkt. Änderungen werden automatisch gespeichert.</p>
          <div class="device"><p class="lock-status" aria-live="polite"></p><button class="text-button refresh">Status prüfen</button><button class="text-button unlock">Jetzt entsperren</button></div>
          <p class="help runtime-status"></p>
          <div class="message" role="status" aria-live="polite"></div>
          <div class="footer"><span class="save-state"></span><div><button class="text-button retry" hidden>Erneut speichern</button><button class="text-button reload" hidden>Neu laden</button></div></div>
        </dialog>`;
      this.$ = selector => this.shadowRoot.querySelector(selector);
      this.$('.launcher').onclick = () => this._open();
      this.$('.close').onclick = () => this._close();
      this.$('dialog').addEventListener('cancel', event => {event.preventDefault(); this._close();});
      this.$('.add').onclick = () => this._add();
      this.$('.plan-toggle').onclick = () => {this._draft.enabled = !this._draft.enabled; this._save();};
      this.$('.refresh').onclick = () => this._refreshLock();
      this.$('.unlock').onclick = () => this._unlock();
      this.$('.retry').onclick = () => this._save();
      this.$('.reload').onclick = () => this._load();
    }
    async _call(type, data={}) {
      return this._hass.callWS({type:`trv_scheduler/${type}`,entity_id:this._config.entity,...data});
    }
    async _open() {
      if (!this._hass || this.$('dialog').open) return;
      this._generation++;
      this._dirty = false;
      this.$('.subtitle').textContent = this._config.name || this._hass.states[this._config.entity]?.attributes.friendly_name || this._config.entity;
      this.$('dialog').showModal();
      await this._load();
      clearInterval(this._poll);
      this._poll = setInterval(() => this._pollState(), 15000);
    }
    _close() {
      if (this._busy) {this._message('Speichervorgang läuft. Bitte kurz warten.'); return;}
      if (this._picker) {this._finishPicker(false);return;}
      if (this._dirty && !window.confirm('Nicht gespeicherte Änderungen verwerfen?')) return;
      this._generation++;
      this._reading=false;
      this.$('dialog').close();
      clearInterval(this._poll);
      this.$('.launcher').focus();
    }
    _message(text='', error=false) {
      this.$('.message').textContent = text;
      this.$('.message').classList.toggle('error', error);
    }
    _controls() {
      const disabled = this._busy || !this._canEdit || !this._draft || !!this._picker;
      this.shadowRoot.querySelectorAll('tbody input,tbody button,.plan-toggle,.add,.retry').forEach(el => {if(!el.closest('.picker-row'))el.disabled = disabled;});
      this.shadowRoot.querySelectorAll('.lock').forEach(el => el.disabled = disabled || !this._state?.lock_supported);
      this.$('.unlock').disabled = this._busy || this._reading || !this._canEdit || !!this._picker;
      this.$('.refresh').disabled = this._busy || this._reading;
      this.$('.reload').disabled = this._busy || !!this._picker;
    }
    async _load() {
      this._picker = null;
      const generation = this._generation;
      this._busy = true; this._controls(); this._message('Zeitplan wird geladen …');
      try {
        const state = await this._call('get');
        if (generation !== this._generation) return;
        this._state = state; this._canEdit = state.can_edit;
        this._draft = structuredClone(state.schedule); this._dirty = false;
        this.$('.reload').hidden = true; this.$('.retry').hidden = true;
        this._message(); this._render();
      } catch (error) {
        if (generation === this._generation) {
          this._draft = null;
          this._message(error.code === 'not_found' ? 'Für dieses Thermostat zuerst die Integration „TRV Zeitsteuerung“ einrichten.' : 'Zeitplan konnte nicht geladen werden.', true);
          this.$('.reload').hidden = false;
        }
      } finally {this._busy = false; this._controls();}
    }
    _render() {
      if (!this._draft) return;
      const focused = this.shadowRoot.activeElement;
      const focusKey = focused?.dataset.focusKey;
      this.$('.plan-toggle').setAttribute('aria-checked', String(this._draft.enabled));
      this.$('.unit').textContent = this._state.temperature_unit || '°C';
      const body = this.$('tbody'); body.replaceChildren();
      const rows = [...this._draft.rows].sort((a,b) => a.time.localeCompare(b.time));
      rows.forEach(row => {
        const tr = document.createElement('tr'); tr.className = row.enabled ? '' : 'paused';
        const cell = element => {const td=document.createElement('td');td.append(element);tr.append(td);};
        const time = document.createElement('input'); time.type='text';time.inputMode='numeric';time.placeholder='HH:MM';time.pattern='(?:[01][0-9]|2[0-3]):[0-5][0-9]';time.value=row.time;time.required=true;
        time.onfocus=()=>time.select();
        time.oninput=()=>{if(/^\d{4}$/.test(time.value))time.value=time.value.slice(0,2)+':'+time.value.slice(2);};
        time.setAttribute('aria-label',`Uhrzeit ${row.time}`);time.dataset.focusKey=`time-${row.id}`;
        time.onchange=()=>{if(time.checkValidity()){row.time=time.value;this._save();}else time.reportValidity();};this._bindPicker(time,row,'time');cell(time);
        const temp = document.createElement('input');temp.type='number';temp.inputMode='decimal';temp.required=true;temp.value=row.temperature;
        temp.min=this._state.limits?.min ?? 4;temp.max=this._state.limits?.max ?? 30;temp.step=this._state.limits?.step || 'any';
        temp.setAttribute('aria-label',`Zieltemperatur ${row.time}`);temp.dataset.focusKey=`temp-${row.id}`;
        temp.onchange=()=>{if(temp.checkValidity()){row.temperature=Number(temp.value);this._save();}else temp.reportValidity();};this._bindPicker(temp,row,'temperature');cell(temp);
        const active=document.createElement('button');active.className='switch';active.innerHTML='<span></span>';active.setAttribute('role','switch');
        active.setAttribute('aria-label',`Schaltzeit ${row.time} aktivieren`);active.setAttribute('aria-checked',String(row.enabled));
        active.onclick=()=>{row.enabled=!row.enabled;this._save();};cell(active);
        const lock=document.createElement('button');lock.className='icon lock';lock.innerHTML=icon(row.locked?'locked':'unlocked');lock.setAttribute('aria-pressed',String(!!row.locked));
        lock.setAttribute('aria-label',`Drehring ab ${row.time} sperren`);lock.title=row.locked?'Drehring ab dieser Uhrzeit gesperrt':'Drehring ab dieser Uhrzeit bedienbar';
        lock.onclick=()=>{row.locked=!row.locked;this._save();};cell(lock);
        const remove=document.createElement('button');remove.className='icon delete';remove.innerHTML=icon('trash');remove.setAttribute('aria-label',`Schaltzeit ${row.time} löschen`);
        remove.onclick=()=>{
          if(!window.confirm(`Schaltzeit um ${row.time} mit ${row.temperature} ${this._state.temperature_unit || '°C'} wirklich löschen?`))return;
          this._draft.rows=this._draft.rows.filter(r=>r.id!==row.id);this._save();
        };cell(remove);
        body.append(tr);
      });
      this.$('.empty').hidden=rows.length>0;
      this.$('.device').hidden=!this._state.lock_supported;
      this._renderLock();this._controls();
      this.$('.save-state').textContent=this._dirty?'Noch nicht gespeichert':this._draft.enabled?'Zeitplan aktiv · täglich':'Zeitplan pausiert';
      if(focusKey) [...body.querySelectorAll('input')].find(el=>el.dataset.focusKey===focusKey)?.focus();
    }
    _bindPicker(input,row,kind) {
      if(!this._useWheels())return;
      input.readOnly=true;input.inputMode='none';
      input.setAttribute('aria-expanded','false');
      input.setAttribute('aria-controls','value-picker');
      const open=()=>this._openPicker(row,kind,input);
      input.onclick=open;
      input.onkeydown=event=>{if(['Enter',' ','ArrowDown'].includes(event.key)){event.preventDefault();open();}};
    }
    _makeWheel(label,values,initial,format) {
      const element=document.createElement('div');element.className='wheel';element.tabIndex=0;
      element.setAttribute('role','spinbutton');element.setAttribute('aria-label',label);
      element.setAttribute('aria-valuemin',String(values[0]));element.setAttribute('aria-valuemax',String(values.at(-1)));
      const options=values.map((value,index)=>{
        const option=document.createElement('div');option.className='wheel-value';option.textContent=format(value);option.setAttribute('aria-hidden','true');
        option.onclick=()=>select(index);
        element.append(option);return option;
      });
      let selected=-1;
      const read=()=>{
        const index=Math.max(0,Math.min(values.length-1,Math.round(element.scrollTop/44)));
        if(index!==selected){options[selected]?.classList.remove('selected');selected=index;options[index].classList.add('selected');}
        element.setAttribute('aria-valuenow',String(values[index]));element.setAttribute('aria-valuetext',format(values[index]));
        return values[index];
      };
      const select=index=>{element.scrollTop=Math.max(0,Math.min(values.length-1,index))*44;read();};
      element.addEventListener('scroll',read,{passive:true});
      element.onkeydown=event=>{
        const moves={ArrowUp:1,ArrowRight:1,ArrowDown:-1,ArrowLeft:-1,PageUp:10,PageDown:-10};
        if(event.key in moves){event.preventDefault();read();select(selected+moves[event.key]);}
        else if(event.key==='Home'||event.key==='End'){event.preventDefault();select(event.key==='Home'?0:values.length-1);}
      };
      return {element,read,init:()=>select(values.reduce((best,v,i)=>Math.abs(v-initial)<Math.abs(values[best]-initial)?i:best,0))};
    }
    _openPicker(row,kind,input) {
      if(this._busy||!this._canEdit||this._picker)return;
      const pickerRow=document.createElement('tr');pickerRow.className='picker-row';
      const cell=document.createElement('td');cell.colSpan=5;pickerRow.append(cell);
      const panel=document.createElement('section');panel.className='picker';panel.id='value-picker';panel.setAttribute('role','group');
      panel.setAttribute('aria-label',kind==='time'?'Uhrzeit auswählen':'Temperatur auswählen');cell.append(panel);
      const title=document.createElement('p');title.className='picker-title';title.textContent=kind==='time'?'Uhrzeit auswählen':`Temperatur ab ${row.time}`;panel.append(title);
      const labels=document.createElement('div');labels.className='wheel-labels';labels.setAttribute('aria-hidden','true');panel.append(labels);
      const stage=document.createElement('div');stage.className='wheel-stage';panel.append(stage);
      let wheels;
      const pad=value=>String(value).padStart(2,'0');
      if(kind==='time') {
        const [hours,minutes]=row.time.split(':').map(Number);
        wheels=[this._makeWheel('Stunden',Array.from({length:24},(_,i)=>i),hours,pad),this._makeWheel('Minuten',Array.from({length:60},(_,i)=>i),minutes,pad)];
        labels.innerHTML='<span>Stunden</span><span>Minuten</span>';
        stage.append(wheels[0].element);
        const colon=document.createElement('span');colon.className='wheel-colon';colon.textContent=':';colon.setAttribute('aria-hidden','true');stage.append(colon,wheels[1].element);
      } else {
        const min=this._state.limits?.min??4,max=this._state.limits?.max??30,step=this._state.limits?.step||.5;
        const first=Math.ceil(min/step-1e-8),last=Math.floor(max/step+1e-8);
        if(last<first||last-first>5000){this._message('Für dieses Gerät ist keine Drehradauswahl verfügbar.',true);return;}
        const values=Array.from({length:last-first+1},(_,i)=>Number(((first+i)*step).toFixed(8)));
        // Preserve a pre-existing off-grid value until the user deliberately changes it.
        if(!values.includes(row.temperature))values.push(row.temperature);
        values.sort((a,b)=>a-b);
        const unit=this._state.temperature_unit||'°C';
        const format=value=>`${value.toLocaleString('de-DE',{maximumFractionDigits:8})} ${unit}`;
        wheels=[this._makeWheel('Zieltemperatur',values,row.temperature,format)];
        labels.innerHTML='<span>Zieltemperatur</span>';stage.append(wheels[0].element);
      }
      const actions=document.createElement('div');actions.className='picker-actions';
      const cancel=document.createElement('button');cancel.className='text-button';cancel.textContent='Abbrechen';cancel.onclick=()=>this._finishPicker(false);
      const apply=document.createElement('button');apply.className='picker-apply';apply.textContent='Übernehmen';apply.onclick=()=>this._finishPicker(true);
      actions.append(cancel,apply);panel.append(actions);
      this._picker={row,kind,input,wheels,pickerRow};
      input.setAttribute('aria-expanded','true');input.closest('tr').after(pickerRow);
      this._controls();
      wheels.forEach(wheel=>wheel.init());
      // Focus the accessible wheel without invoking the iOS keyboard.
      wheels[0].element.focus({preventScroll:true});
      panel.scrollIntoView({block:'nearest',behavior:'instant'});
    }
    _finishPicker(commit) {
      const picker=this._picker;if(!picker)return;
      const values=picker.wheels.map(wheel=>wheel.read());
      const value=picker.kind==='time'?values.map(v=>String(v).padStart(2,'0')).join(':'):values[0];
      const changed=commit&&picker.row[picker.kind]!==value;
      this._picker=null;picker.pickerRow.remove();picker.input.setAttribute('aria-expanded','false');
      this._controls();
      if(changed){
        picker.row[picker.kind]=value;
        const key=picker.input.dataset.focusKey;
        this._save().then(()=>{if(this.$('dialog').open)[...this.shadowRoot.querySelectorAll('tbody input')].find(el=>el.dataset.focusKey===key)?.focus({preventScroll:true});});
      } else picker.input.focus({preventScroll:true});
    }
    _add() {
      if(this._draft.rows.length>=48){this._message('Maximal 48 Schaltzeiten pro Thermostat.',true);return;}
      let minute=12*60;
      const used=new Set(this._draft.rows.map(r=>r.time));
      const format=m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
      while(used.has(format(minute))) minute=(minute+15)%1440;
      const id=Array.from(crypto.getRandomValues(new Uint8Array(12)),b=>b.toString(16).padStart(2,'0')).join('');
      const min=this._state.limits?.min??4,max=this._state.limits?.max??30,step=this._state.limits?.step||.5;
      const raw=this._hass.states[this._config.entity]?.attributes.temperature??21;
      const temperature=Math.min(max,Math.max(min,Math.round(raw/step)*step));
      // New rows start paused; setting a time must not accidentally schedule a draft.
      this._draft.rows.push({id,time:format(minute),temperature,enabled:false,locked:false});
      this._save();
    }
    async _save() {
      if(this._busy||!this._canEdit)return;
      this._dirty=true;this._busy=true;this._controls();this._message('Wird gespeichert …');
      try {
        const state=await this._call('replace',{expected_revision:this._draft.revision,enabled:this._draft.enabled,rows:this._draft.rows});
        this._state={...this._state,...state};this._draft=structuredClone(state.schedule);this._dirty=false;
        this.$('.reload').hidden=true;this.$('.retry').hidden=true;
        this._message('Gespeichert.');
      } catch(error) {
        const conflict=error.code==='revision_conflict';
        this._message(conflict?'An anderer Stelle geändert. Bitte neu laden; deine Eingabe wurde nicht überschrieben.':`Nicht gespeichert: ${error.message||'Verbindung prüfen und erneut versuchen.'}`,true);
        this.$('.reload').hidden=false;this.$('.retry').hidden=conflict;
      } finally {this._busy=false;this._render();}
    }
    _renderLock() {
      const state=this._state?.device_lock;
      const result=this._state?.last_result;
      const status={sent:'ausgeführt',failed:'fehlgeschlagen',blocked:'Heizung nicht freigegeben',missed:'verpasst',busy:'Gerät war beschäftigt'};
      this.$('.runtime-status').textContent=this._state?.gate_enabled===false?'Heizung ist nicht freigegeben. Schaltzeiten werden ausgelassen.':result?`Letzter Schaltpunkt: ${new Date(result.scheduled_at).toLocaleString('de-DE')} · ${status[result.status]||result.status}`:'';
      this.$('.lock-status').textContent=this._reading?'Gerätesperre wird abgefragt …':state?.error?`Gerätesperre unbestätigt: ${state.error}`:state?.locked===true?'Drehring am Gerät gesperrt':state?.locked===false?'Drehring am Gerät freigegeben':'Gerätestatus noch nicht abgefragt';
      if(!this._reading&&state?.checked_at&&!state.error)this.$('.lock-status').textContent+=` · Stand ${new Date(state.checked_at).toLocaleTimeString('de-DE')}`;
    }
    async _refreshLock() {
      if(this._reading||!this._state?.lock_supported)return;
      const generation=this._generation;
      this._reading=true;this._renderLock();this._controls();
      try {
        const state=await this._call('lock_status');
        if(generation===this._generation)this._state.device_lock=state.device_lock;
      } catch {if(generation===this._generation)this._state.device_lock={error:'Abfrage fehlgeschlagen.'};}
      finally {if(generation===this._generation){this._reading=false;this._renderLock();this._controls();}}
    }
    async _unlock() {
      if(this._busy||this._reading||!this._canEdit)return;
      this._busy=true;this._controls();this._message('Gerät wird entsperrt …');
      try {
        const state=await this._call('unlock');this._state.device_lock=state.device_lock;
        this._message('Drehring freigegeben. Der nächste aktive Schaltpunkt gilt wieder.');
      } catch(error) {this._message(error.message||'Entsperren nicht bestätigt.',true);}
      finally {this._busy=false;this._renderLock();this._controls();}
    }
    async _pollState() {
      if(!this.$('dialog').open||this._busy||this._dirty||!this._state)return;
      try {
        const generation=this._generation;
        const state=await this._call('get');
        if(generation!==this._generation||this._busy||this._dirty)return;
        this._state.device_lock=state.device_lock;this._state.last_result=state.last_result;this._state.gate_enabled=state.gate_enabled;this._renderLock();
        if(state.schedule.revision!==this._draft.revision){this._message('Zeitplan wurde an anderer Stelle geändert. Bitte neu laden.',true);this.$('.reload').hidden=false;}
      } catch { /* Keep the last displayed state; the next explicit action reports errors. */ }
    }
  }
  customElements.define('trv-scheduler-card',TRVSchedulerCard);
  window.customCards=window.customCards||[];
  window.customCards.push({type:'trv-scheduler-card',name:'TRV Zeitsteuerung',description:'Tägliche Schaltzeiten mit Temperatur und Gerätesperre im Dialog',preview:false});
})();
