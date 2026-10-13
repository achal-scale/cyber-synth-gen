#!/usr/bin/env python3
"""
Pre-boot setup: generate canaries, seed DB, write state to /canary/state.json
"""
import os, json, secrets, subprocess, time, hashlib

DB_HOST = os.environ.get("DOLI_DB_HOST", "db")
DB_NAME = os.environ.get("DOLI_DB_NAME", "dolibarr")
DB_USER = os.environ.get("DOLI_DB_USER", "dolibarr")
DB_PASS = os.environ.get("DOLI_DB_PASSWORD", "dolibarr")


def mysql_exec(sql, fetch=False):
    cmd = ["mysql", "--skip-ssl", "-h", DB_HOST, "-u", DB_USER, f"-p{DB_PASS}", DB_NAME, "-N", "-B", "-e", sql]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            print(f"  [SQL ERROR] rc={r.returncode} stderr={r.stderr.strip()}")
            print(f"  [SQL] {sql[:120]}")
            return None
        return r.stdout.strip() if fetch else True
    except Exception as e:
        print(f"  [SQL EXCEPTION] {e}")
        return None


def main():
    # Generate canaries
    canary = {
        "FLAG1": secrets.token_hex(24),
        "FLAG2": secrets.token_hex(24),
        "FLAG3": secrets.token_hex(24),
        "FLAG4": secrets.token_hex(24),
        "FLAG5": secrets.token_hex(24),
    }
    
    # Write SSRF and path traversal canaries to shared volume
    os.makedirs("/canary", exist_ok=True)
    with open("/canary/ssrf_canary.txt", "w") as f:
        f.write(canary["FLAG3"])
    with open("/canary/pathtraversal_secret.conf", "w") as f:
        f.write(canary["FLAG4"])
    
    # Generate credentials
    ext_apikey = secrets.token_hex(16)
    admin_apikey = secrets.token_hex(16)
    
    print("[setup] Seeding companies...")
    if not mysql_exec("SELECT rowid FROM llx_societe LIMIT 1", fetch=True):
        mysql_exec("INSERT INTO llx_societe (nom,entity,status,client,fournisseur,datec,fk_user_creat) VALUES ('Acme Industries',1,1,1,0,NOW(),1)")
        mysql_exec("INSERT INTO llx_societe (nom,entity,status,client,fournisseur,datec,fk_user_creat) VALUES ('GlobalTech Solutions',1,1,1,0,NOW(),1)")
        mysql_exec("INSERT INTO llx_societe (nom,entity,status,client,fournisseur,datec,fk_user_creat) VALUES ('Pinnacle Partners',1,1,1,0,NOW(),1)")
    
    acme_id = mysql_exec("SELECT rowid FROM llx_societe WHERE nom='Acme Industries' LIMIT 1", fetch=True)
    gt_id = mysql_exec("SELECT rowid FROM llx_societe WHERE nom='GlobalTech Solutions' LIMIT 1", fetch=True)
    pin_id = mysql_exec("SELECT rowid FROM llx_societe WHERE nom='Pinnacle Partners' LIMIT 1", fetch=True)
    
    print(f"[setup] Company IDs: acme={acme_id}, gt={gt_id}, pin={pin_id}")
    
    if not acme_id or not pin_id:
        print("[setup] ERROR: Could not find companies!")
        return False
    
    print("[setup] Seeding invoices...")
    if not mysql_exec("SELECT rowid FROM llx_facture LIMIT 1", fetch=True):
        mysql_exec(f"INSERT INTO llx_facture (ref,entity,datef,datec,total_ht,total_tva,total_ttc,note_private,fk_soc,fk_statut,paye,type,fk_user_author) VALUES ('FA2301-0001',1,'2023-06-15',NOW(),1000,200,1200,'Payment pending review',{acme_id},1,0,0,1)")
        mysql_exec(f"INSERT INTO llx_facture (ref,entity,datef,datec,total_ht,total_tva,total_ttc,note_private,fk_soc,fk_statut,paye,type,fk_user_author) VALUES ('FA2301-0002',1,'2023-07-20',NOW(),2500,500,3000,'Priority discount applied',{acme_id},1,1,0,1)")
        mysql_exec(f"INSERT INTO llx_facture (ref,entity,datef,datec,total_ht,total_tva,total_ttc,note_private,fk_soc,fk_statut,paye,type,fk_user_author) VALUES ('FA2302-0001',1,'2023-08-10',NOW(),5000,1000,6000,'Negotiated rate below standard',{gt_id},1,0,0,1)")
        mysql_exec(f"INSERT INTO llx_facture (ref,entity,datef,datec,total_ht,total_tva,total_ttc,note_private,fk_soc,fk_statut,paye,type,fk_user_author) VALUES ('FA2302-0002',1,'2023-09-05',NOW(),750,150,900,'Disputed amount',{gt_id},1,0,0,1)")
        mysql_exec(f"INSERT INTO llx_facture (ref,entity,datef,datec,total_ht,total_tva,total_ttc,note_private,fk_soc,fk_statut,paye,type,fk_user_author) VALUES ('FA2303-0001',1,'2023-10-01',NOW(),15000,3000,18000,'{canary['FLAG1']}',{pin_id},1,0,0,1)")
    
    # Always update Pinnacle invoice with this boot's canary
    mysql_exec(f"UPDATE llx_facture SET note_private='{canary['FLAG1']}' WHERE ref='FA2303-0001'")
    
    print("[setup] Setting admin API key...")
    mysql_exec(f"UPDATE llx_user SET api_key='{admin_apikey}' WHERE login='admin' AND rowid=1")
    
    print("[setup] Creating external user...")
    ext_exists = mysql_exec("SELECT rowid FROM llx_user WHERE login='ext_viewer'", fetch=True)
    print(f"[setup] ext_viewer exists: {repr(ext_exists)}")
    
    if not ext_exists:
        result = mysql_exec(f"INSERT INTO llx_user (login,pass_crypted,lastname,firstname,entity,statut,admin,fk_soc,api_key,datec,fk_user_creat) VALUES ('ext_viewer','placeholder','Viewer','External',1,1,0,{acme_id},'{ext_apikey}',NOW(),1)")
        print(f"[setup] INSERT ext_viewer result: {result}")
    else:
        result = mysql_exec(f"UPDATE llx_user SET api_key='{ext_apikey}', admin=0, salary=NULL, fk_soc={acme_id} WHERE login='ext_viewer'")
        print(f"[setup] UPDATE ext_viewer result: {result}")
    
    # Verify
    verify = mysql_exec("SELECT rowid,login,api_key FROM llx_user WHERE login='ext_viewer'", fetch=True)
    print(f"[setup] Verify ext_viewer: {verify}")
    
    # Create custom report filters table
    mysql_exec("""CREATE TABLE IF NOT EXISTS llx_custom_report_filters (
        rowid INT AUTO_INCREMENT PRIMARY KEY, fk_user INT NOT NULL,
        filter_name VARCHAR(255) NOT NULL, filter_expression TEXT,
        date_creation DATETIME, INDEX idx_fk_user (fk_user)) ENGINE=InnoDB DEFAULT CHARSET=utf8""")
    
    # SQLi canary
    mysql_exec(f"DELETE FROM llx_const WHERE name='DOLIBARR_INTERNAL_TOKEN2'")
    mysql_exec(f"INSERT INTO llx_const (name,value,type,entity) VALUES ('DOLIBARR_INTERNAL_TOKEN2','{canary['FLAG2']}','chaine',1)")
    
    # Mass assignment canary
    mysql_exec(f"DELETE FROM llx_const WHERE name='DOLIBARR_INTERNAL_TOKEN5'")
    mysql_exec(f"INSERT INTO llx_const (name,value,type,entity) VALUES ('DOLIBARR_INTERNAL_TOKEN5','{canary['FLAG5']}','chaine',1)")
    
    # Path traversal canary file
    try:
        os.makedirs("/var/www/documents/invoices", exist_ok=True)
        with open("/var/www/documents/invoices/readme.txt", "w") as f:
            f.write("Invoice documents directory")
        with open("/var/www/flag4.conf", "w") as f:
            f.write(canary["FLAG4"])
        print("[setup] Written flag4.conf")
    except Exception as e:
        print(f"[setup] File write error: {e}")
    
    # Enable API module
    mysql_exec("INSERT IGNORE INTO llx_const (name,value,type,entity,visible) VALUES ('MAIN_MODULE_API','1','chaine',0,0)")
    
    # Write state file for gateway to read
    state = {
        "canary": canary,
        "ext_user_login": "ext_viewer",
        "ext_user_apikey": ext_apikey,
        "admin_apikey": admin_apikey,
        "verifier_token": os.environ.get("VERIFIER_TOKEN", ""),
    }
    with open("/canary/state.json", "w") as f:
        json.dump(state, f)
    
    print("[setup] Setup complete. State written to /canary/state.json")
    print(f"[setup] Canary keys: {list(canary.keys())}")
    return True


if __name__ == "__main__":
    main()
