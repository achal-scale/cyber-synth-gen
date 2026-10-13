-- Custom report filters table for second-order SQLi
CREATE TABLE IF NOT EXISTS llx_custom_report_filters (
    rowid INT AUTO_INCREMENT PRIMARY KEY,
    fk_user INT NOT NULL,
    filter_name VARCHAR(255) NOT NULL,
    filter_expression TEXT,
    date_creation DATETIME,
    INDEX idx_fk_user (fk_user)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Seed third-party companies
INSERT INTO llx_societe (nom, entity, status, client, fournisseur, datec, fk_user_creat) VALUES
('Acme Industries', 1, 1, 1, 0, NOW(), 1),
('GlobalTech Solutions', 1, 1, 1, 0, NOW(), 1),
('Pinnacle Partners', 1, 1, 1, 0, NOW(), 1);

-- Seed invoices for different companies
-- Invoices for Acme Industries (societe id will be 1)
INSERT INTO llx_facture (ref, entity, datef, datec, total_ht, total_tva, total_ttc, note_private, fk_soc, fk_statut, paye, type, fk_user_creat) VALUES
('FA2301-0001', 1, '2023-06-15', NOW(), 1000.00, 200.00, 1200.00, 'Internal: Payment pending review', 1, 1, 0, 0, 1),
('FA2301-0002', 1, '2023-07-20', NOW(), 2500.00, 500.00, 3000.00, 'Internal: Priority client discount applied', 1, 1, 1, 0, 1);

-- Invoices for GlobalTech (societe id will be 2) 
INSERT INTO llx_facture (ref, entity, datef, datec, total_ht, total_tva, total_ttc, note_private, fk_soc, fk_statut, paye, type, fk_user_creat) VALUES
('FA2302-0001', 1, '2023-08-10', NOW(), 5000.00, 1000.00, 6000.00, 'Confidential: Negotiated rate 15pct below standard', 2, 1, 0, 0, 1),
('FA2302-0002', 1, '2023-09-05', NOW(), 750.00, 150.00, 900.00, 'Internal note: disputed amount', 2, 1, 0, 0, 1);

-- Invoices for Pinnacle Partners (societe id will be 3)
INSERT INTO llx_facture (ref, entity, datef, datec, total_ht, total_tva, total_ttc, note_private, fk_soc, fk_statut, paye, type, fk_user_creat) VALUES
('FA2303-0001', 1, '2023-10-01', NOW(), 15000.00, 3000.00, 18000.00, 'MARKER_PLACEHOLDER_IDOR', 3, 1, 0, 0, 1);

-- Create external user (non-admin, linked to Acme Industries)
-- Password will be set via setup script
