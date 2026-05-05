import type {
  Enquiry, Personnel, Asset, Project, StockItem, Invoice,
  Payment, Supplier, PurchaseOrder, Workflow, Persona, Channel,
  WikiPage, DashboardMetric, Notification, DynamicUI, RagDocument,
} from '@/types';

// ─── 12 Enquiries ───
const enquiries: Enquiry[] = [
  { id: 'enq-001', client: 'ADNOC', contactName: 'Ahmed Al-Rashid', email: 'ahmed.r@adnoc.ae', phone: '+971 2 603 0000', service: 'ROV Inspection', value: 450000, currency: 'AED', status: 'approved', assignedTo: 'Omar Hassan', date: '2026-05-01', description: 'Pipeline inspection at Upper Zakum field using ROV', notes: ['Client prefers weekend operations'] },
  { id: 'enq-002', client: 'ZADCO', contactName: 'Khalid Al-Mansouri', email: 'khalid.m@zadco.ae', phone: '+971 2 602 3000', service: 'Crane Rental', value: 280000, currency: 'AED', status: 'proposal', assignedTo: 'Sarah Johnson', date: '2026-04-28', description: 'Offshore crane rental for platform maintenance', notes: ['Require 50-ton capacity'] },
  { id: 'enq-003', client: 'Saudi Aramco', contactName: 'Faisal Al-Qahtani', email: 'faisal.q@aramco.com', phone: '+966 13 872 0000', service: 'Diving Support', value: 720000, currency: 'SAR', status: 'negotiation', assignedTo: 'Omar Hassan', date: '2026-04-25', description: 'Deep sea diving support for jacket inspection', notes: ['BOSIET certification required'] },
  { id: 'enq-004', client: 'Qatar Petroleum', contactName: 'Nasser Al-Kuwari', email: 'nasser.k@qp.com.qa', phone: '+974 4013 0000', service: 'NDT Inspection', value: 195000, currency: 'QAR', status: 'qualified', assignedTo: 'Priya Sharma', date: '2026-04-22', description: 'Ultrasonic testing of storage tanks', notes: ['Schedule for Ramadan'] },
  { id: 'enq-005', client: 'Borouge', contactName: 'Mohammed Al-Zaabi', email: 'mohammed.z@borouge.com', phone: '+971 2 607 0000', service: 'Subsea Cable Laying', value: 890000, currency: 'AED', status: 'new', assignedTo: 'Unassigned', date: '2026-05-03', description: 'Fiber optic cable installation between platforms', notes: [] },
  { id: 'enq-006', client: 'Dubai Petroleum', contactName: 'Rashid Al-Falasi', email: 'rashid.f@dubaipetroleum.ae', phone: '+971 4 337 0000', service: 'ROV Inspection', value: 320000, currency: 'AED', status: 'approved', assignedTo: 'Omar Hassan', date: '2026-04-15', description: 'FPSO hull inspection', notes: ['Annual contract'] },
  { id: 'enq-007', client: 'ADMA-OPCO', contactName: 'Sultan Al-Hameli', email: 'sultan.h@adma.ae', phone: '+971 2 602 8000', service: 'Survey Services', value: 560000, currency: 'AED', status: 'proposal', assignedTo: 'Sarah Johnson', date: '2026-04-30', description: 'Bathymetric survey of new drilling location', notes: ['Require multibeam sonar'] },
  { id: 'enq-008', client: 'Kuwait Oil Company', contactName: 'Waleed Al-Ajmi', email: 'waleed.a@koc.kw', phone: '+965 2398 0000', service: 'Diving Support', value: 410000, currency: 'KWD', status: 'qualified', assignedTo: 'Priya Sharma', date: '2026-04-18', description: 'Underwater welding at offshore structure', notes: ['Hot work permit needed'] },
  { id: 'enq-009', client: 'BAPCO', contactName: 'Ali Al-Baharna', email: 'ali.b@bapco.net', phone: '+973 1775 0000', service: 'NDT Inspection', value: 175000, currency: 'BHD', status: 'negotiation', assignedTo: 'Omar Hassan', date: '2026-05-02', description: 'Radiographic testing of process piping', notes: ['Safety standby required'] },
  { id: 'enq-010', client: 'Oxy Oman', contactName: 'Yusuf Al-Busaidi', email: 'yusuf.b@oxy.com', phone: '+968 2476 0000', service: 'Crane Rental', value: 230000, currency: 'OMR', status: 'new', assignedTo: 'Unassigned', date: '2026-05-04', description: 'Mobile crane for onshore module lift', notes: ['Road permit required'] },
  { id: 'enq-011', client: 'PDO', contactName: 'Salim Al-Harthi', email: 'salim.h@pdo.co.om', phone: '+968 2467 0000', service: 'ROV Inspection', value: 680000, currency: 'OMR', status: 'proposal', assignedTo: 'Sarah Johnson', date: '2026-04-20', description: 'Riser inspection and anode survey', notes: ['Client requires video streaming'] },
  { id: 'enq-012', client: 'TAKREER', contactName: 'Hamed Al-Shamsi', email: 'hamed.s@takreer.ae', phone: '+971 2 602 0000', service: 'Communication Systems', value: 145000, currency: 'AED', status: 'qualified', assignedTo: 'Priya Sharma', date: '2026-04-26', description: 'Upgrade of offshore UHF radio network', notes: ['Integration with existing system'] },
];

// ─── 15 Personnel ───
const personnel: Personnel[] = [
  { id: 'emp-001', name: 'Omar Hassan', role: 'Operations Manager', department: 'Operations', email: 'omar.h@ariesmarine.ae', phone: '+971 50 111 2222', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'BOSIET', status: 'valid', expiryDate: '2027-03-15', level: 'OPITO' }, { name: 'HUET', status: 'valid', expiryDate: '2027-03-15' }, { name: 'IRATA L3', status: 'valid', expiryDate: '2026-11-20', level: 'Level 3' }] },
  { id: 'emp-002', name: 'Sarah Johnson', role: 'Sales Manager', department: 'Sales', email: 'sarah.j@ariesmarine.ae', phone: '+971 50 222 3333', location: 'Dubai', avatar: '', certifications: [{ name: 'NEBOSH', status: 'valid', expiryDate: '2028-01-10' }] },
  { id: 'emp-003', name: 'Priya Sharma', role: 'Technical Engineer', department: 'Engineering', email: 'priya.s@ariesmarine.ae', phone: '+971 50 333 4444', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'BOSIET', status: 'expiring', expiryDate: '2026-05-20', level: 'OPITO' }, { name: 'CSWIP', status: 'valid', expiryDate: '2027-08-15' }] },
  { id: 'emp-004', name: 'Mohammed Al-Farsi', role: 'ROV Pilot', department: 'Operations', email: 'mohammed.f@ariesmarine.ae', phone: '+971 50 444 5555', location: 'Das Island', avatar: '', certifications: [{ name: 'BOSIET', status: 'valid', expiryDate: '2027-02-10' }, { name: 'ROV Pilot', status: 'valid', expiryDate: '2027-06-30', level: 'Tech 2' }, { name: 'IRATA L2', status: 'valid', expiryDate: '2026-09-15', level: 'Level 2' }] },
  { id: 'emp-005', name: 'Lisa Chen', role: 'NDT Specialist', department: 'Inspection', email: 'lisa.c@ariesmarine.ae', phone: '+971 50 555 6666', location: 'Jebel Ali', avatar: '', certifications: [{ name: 'ASNT Level II', status: 'valid', expiryDate: '2027-04-22' }, { name: 'BOSIET', status: 'valid', expiryDate: '2027-01-05' }] },
  { id: 'emp-006', name: 'Rashid Khan', role: 'Diving Supervisor', department: 'Operations', email: 'rashid.k@ariesmarine.ae', phone: '+971 50 666 7777', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'BOSIET', status: 'valid', expiryDate: '2026-12-18' }, { name: 'ADAS', status: 'valid', expiryDate: '2027-03-10', level: 'Part 4' }, { name: 'HSE', status: 'valid', expiryDate: '2027-05-22' }] },
  { id: 'emp-007', name: 'Fatima Al-Zahra', role: 'Finance Manager', department: 'Finance', email: 'fatima.z@ariesmarine.ae', phone: '+971 50 777 8888', location: 'Dubai', avatar: '', certifications: [{ name: 'CPA', status: 'valid', expiryDate: '2027-12-31' }] },
  { id: 'emp-008', name: 'James Wilson', role: 'Crane Operator', department: 'Operations', email: 'james.w@ariesmarine.ae', phone: '+971 50 888 9999', location: 'Mussafah', avatar: '', certifications: [{ name: 'BOSIET', status: 'expired', expiryDate: '2026-02-28' }, { name: 'CPCS', status: 'valid', expiryDate: '2027-07-15', level: 'A60' }] },
  { id: 'emp-009', name: 'Aisha Bello', role: 'HSE Coordinator', department: 'HSE', email: 'aisha.b@ariesmarine.ae', phone: '+971 50 999 0000', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'NEBOSH', status: 'valid', expiryDate: '2028-03-20' }, { name: 'IOSH', status: 'valid', expiryDate: '2027-11-10' }, { name: 'BOSIET', status: 'valid', expiryDate: '2027-04-05' }] },
  { id: 'emp-010', name: 'Kumar Rajesh', role: 'Electrical Technician', department: 'Maintenance', email: 'kumar.r@ariesmarine.ae', phone: '+971 50 000 1111', location: 'Das Island', avatar: '', certifications: [{ name: 'BOSIET', status: 'valid', expiryDate: '2027-06-12' }, { name: 'IECEx', status: 'valid', expiryDate: '2027-09-30' }] },
  { id: 'emp-011', name: 'Emma Thompson', role: 'Project Coordinator', department: 'Projects', email: 'emma.t@ariesmarine.ae', phone: '+971 55 111 2222', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'PMP', status: 'valid', expiryDate: '2028-02-15' }, { name: 'BOSIET', status: 'valid', expiryDate: '2027-01-30' }] },
  { id: 'emp-012', name: 'Said Al-Rashdi', role: 'Surveyor', department: 'Survey', email: 'said.a@ariesmarine.ae', phone: '+971 55 222 3333', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'BOSIET', status: 'expiring', expiryDate: '2026-05-18' }, { name: 'IHO', status: 'valid', expiryDate: '2027-10-10' }, { name: 'Multibeam', status: 'valid', expiryDate: '2027-07-25' }] },
  { id: 'emp-013', name: 'Nora Okafor', role: 'Procurement Officer', department: 'Procurement', email: 'nora.o@ariesmarine.ae', phone: '+971 55 333 4444', location: 'Dubai', avatar: '', certifications: [] },
  { id: 'emp-014', name: 'Tom Bradley', role: 'ROV Technician', department: 'Operations', email: 'tom.b@ariesmarine.ae', phone: '+971 55 444 5555', location: 'Das Island', avatar: '', certifications: [{ name: 'BOSIET', status: 'valid', expiryDate: '2027-08-10' }, { name: 'ROV Maint', status: 'valid', expiryDate: '2027-04-20' }, { name: 'Electrical', status: 'valid', expiryDate: '2027-06-15' }] },
  { id: 'emp-015', name: 'Hessa Al-Muhairi', role: 'HR Manager', department: 'HR', email: 'hessa.m@ariesmarine.ae', phone: '+971 55 555 6666', location: 'Abu Dhabi', avatar: '', certifications: [{ name: 'CHRP', status: 'valid', expiryDate: '2027-09-01' }] },
];

// ─── 45 Assets ───
const assets: Asset[] = [
  // ROV (10)
  { id: 'ast-001', name: 'Seaeye Falcon DR', category: 'ROV', serialNumber: 'SEF-2021-0042', location: 'Das Island', lastCalibration: '2026-01-15', nextCalibration: '2026-07-15', status: 'calibrated' },
  { id: 'ast-002', name: 'Saab Seaeye Tiger', category: 'ROV', serialNumber: 'SST-2020-0089', location: 'Jebel Ali', lastCalibration: '2025-11-20', nextCalibration: '2026-05-20', status: 'due-soon' },
  { id: 'ast-003', name: 'Forum XLT-30', category: 'ROV', serialNumber: 'FMX-2022-0015', location: 'Mussafah', lastCalibration: '2026-02-10', nextCalibration: '2026-08-10', status: 'calibrated' },
  { id: 'ast-004', name: 'Teledyne SeaBotix vLBV', category: 'ROV', serialNumber: 'TSB-2021-0067', location: 'Das Island', lastCalibration: '2025-10-05', nextCalibration: '2026-04-05', status: 'overdue' },
  { id: 'ast-005', name: 'ECA Group H300 MK2', category: 'ROV', serialNumber: 'ECA-2023-0003', location: 'Abu Dhabi', lastCalibration: '2026-03-01', nextCalibration: '2026-09-01', status: 'calibrated' },
  { id: 'ast-006', name: 'Deep Trekker DTG3', category: 'ROV', serialNumber: 'DTD-2022-0044', location: 'Jebel Ali', lastCalibration: '2025-12-12', nextCalibration: '2026-06-12', status: 'due-soon' },
  { id: 'ast-007', name: 'VideoRay Pro 4', category: 'ROV', serialNumber: 'VRP-2021-0091', location: 'Mussafah', lastCalibration: '2026-01-20', nextCalibration: '2026-07-20', status: 'calibrated' },
  { id: 'ast-008', name: 'Argus Mariner', category: 'ROV', serialNumber: 'ARM-2020-0076', location: 'Das Island', lastCalibration: '2025-09-18', nextCalibration: '2026-03-18', status: 'overdue' },
  { id: 'ast-009', name: 'SMD Quasar', category: 'ROV', serialNumber: 'SMQ-2023-0012', location: 'Abu Dhabi', lastCalibration: '2026-04-05', nextCalibration: '2026-10-05', status: 'calibrated' },
  { id: 'ast-010', name: 'Oceaneering Maxx', category: 'ROV', serialNumber: 'OCM-2022-0038', location: 'Jebel Ali', lastCalibration: '2026-02-28', nextCalibration: '2026-08-28', status: 'calibrated' },
  // NDT (12)
  { id: 'ast-011', name: 'Olympus Epoch 650', category: 'NDT', serialNumber: 'OLE-2021-0023', location: 'Jebel Ali', lastCalibration: '2026-03-10', nextCalibration: '2026-09-10', status: 'calibrated' },
  { id: 'ast-012', name: 'GE Phasor XS', category: 'NDT', serialNumber: 'GEP-2020-0056', location: 'Mussafah', lastCalibration: '2025-11-15', nextCalibration: '2026-05-15', status: 'due-soon' },
  { id: 'ast-013', name: 'Sonatest Veo+', category: 'NDT', serialNumber: 'STV-2022-0018', location: 'Jebel Ali', lastCalibration: '2026-01-22', nextCalibration: '2026-07-22', status: 'calibrated' },
  { id: 'ast-014', name: 'Zetec TOPAZ 32', category: 'NDT', serialNumber: 'ZET-2023-0009', location: 'Das Island', lastCalibration: '2026-04-01', nextCalibration: '2026-10-01', status: 'calibrated' },
  { id: 'ast-015', name: 'Magneflux Y-7', category: 'NDT', serialNumber: 'MFY-2021-0041', location: 'Mussafah', lastCalibration: '2025-12-05', nextCalibration: '2026-06-05', status: 'due-soon' },
  { id: 'ast-016', name: 'Fischer DMP10', category: 'NDT', serialNumber: 'FID-2022-0027', location: 'Jebel Ali', lastCalibration: '2026-02-18', nextCalibration: '2026-08-18', status: 'calibrated' },
  { id: 'ast-017', name: 'PCE UT Meter', category: 'NDT', serialNumber: 'PCU-2020-0063', location: 'Das Island', lastCalibration: '2025-10-20', nextCalibration: '2026-04-20', status: 'overdue' },
  { id: 'ast-018', name: 'Elcometer 456', category: 'NDT', serialNumber: 'ELC-2023-0005', location: 'Mussafah', lastCalibration: '2026-03-25', nextCalibration: '2026-09-25', status: 'calibrated' },
  { id: 'ast-019', name: 'YXLON Smart EVO', category: 'NDT', serialNumber: 'YXS-2021-0035', location: 'Jebel Ali', lastCalibration: '2025-11-30', nextCalibration: '2026-05-30', status: 'due-soon' },
  { id: 'ast-020', name: 'Viscom RTX-200', category: 'NDT', serialNumber: 'VRT-2022-0022', location: 'Das Island', lastCalibration: '2026-01-08', nextCalibration: '2026-07-08', status: 'calibrated' },
  { id: 'ast-021', name: 'Baker Hughes Krautkramer', category: 'NDT', serialNumber: 'BHK-2020-0078', location: 'Mussafah', lastCalibration: '2025-09-25', nextCalibration: '2026-03-25', status: 'overdue' },
  { id: 'ast-022', name: 'Nikon XTH 225', category: 'NDT', serialNumber: 'NIX-2023-0011', location: 'Jebel Ali', lastCalibration: '2026-04-12', nextCalibration: '2026-10-12', status: 'calibrated' },
  // Crane (8)
  { id: 'ast-023', name: 'Liebherr LTM 1050', category: 'Crane', serialNumber: 'LBL-2021-0019', location: 'Mussafah', lastCalibration: '2026-02-15', nextCalibration: '2026-08-15', status: 'calibrated' },
  { id: 'ast-024', name: 'Tadano GR-500EXL', category: 'Crane', serialNumber: 'TDG-2022-0014', location: 'Jebel Ali', lastCalibration: '2025-12-20', nextCalibration: '2026-06-20', status: 'due-soon' },
  { id: 'ast-025', name: 'XCMG XCA220', category: 'Crane', serialNumber: 'XCM-2023-0007', location: 'Mussafah', lastCalibration: '2026-03-01', nextCalibration: '2026-09-01', status: 'calibrated' },
  { id: 'ast-026', name: 'Terex AC 100', category: 'Crane', serialNumber: 'TRA-2020-0042', location: 'Das Island', lastCalibration: '2025-10-10', nextCalibration: '2026-04-10', status: 'overdue' },
  { id: 'ast-027', name: 'Manitowoc MLC150', category: 'Crane', serialNumber: 'MTM-2021-0028', location: 'Jebel Ali', lastCalibration: '2026-01-25', nextCalibration: '2026-07-25', status: 'calibrated' },
  { id: 'ast-028', name: 'Sany SAC6000', category: 'Crane', serialNumber: 'SYS-2022-0011', location: 'Mussafah', lastCalibration: '2025-11-05', nextCalibration: '2026-05-05', status: 'due-soon' },
  { id: 'ast-029', name: 'Kobelco CKE2500G', category: 'Crane', serialNumber: 'KBC-2023-0004', location: 'Das Island', lastCalibration: '2026-04-08', nextCalibration: '2026-10-08', status: 'calibrated' },
  { id: 'ast-030', name: 'Zoomlion ZTC1500', category: 'Crane', serialNumber: 'ZMZ-2021-0033', location: 'Jebel Ali', lastCalibration: '2026-02-01', nextCalibration: '2026-08-01', status: 'calibrated' },
  // Diving (6)
  { id: 'ast-031', name: 'Kirby Morgan EXO-BR', category: 'Diving', serialNumber: 'KME-2022-0016', location: 'Das Island', lastCalibration: '2026-03-12', nextCalibration: '2026-09-12', status: 'calibrated' },
  { id: 'ast-032', name: 'Amron 2830A Comm', category: 'Diving', serialNumber: 'AAC-2021-0031', location: 'Mussafah', lastCalibration: '2025-11-18', nextCalibration: '2026-05-18', status: 'due-soon' },
  { id: 'ast-033', name: 'Subsalva GTX Suit', category: 'Diving', serialNumber: 'SGS-2023-0008', location: 'Das Island', lastCalibration: '2026-01-30', nextCalibration: '2026-07-30', status: 'calibrated' },
  { id: 'ast-034', name: 'Divex AH5 HP', category: 'Diving', serialNumber: 'DAH-2022-0019', location: 'Mussafah', lastCalibration: '2025-10-22', nextCalibration: '2026-04-22', status: 'overdue' },
  { id: 'ast-035', name: 'Interspiro Divator', category: 'Diving', serialNumber: 'ISD-2021-0044', location: 'Das Island', lastCalibration: '2026-02-20', nextCalibration: '2026-08-20', status: 'calibrated' },
  { id: 'ast-036', name: 'Apollo BioSystem', category: 'Diving', serialNumber: 'APB-2023-0006', location: 'Mussafah', lastCalibration: '2026-04-15', nextCalibration: '2026-10-15', status: 'calibrated' },
  // Survey (5)
  { id: 'ast-037', name: 'Teledyne Reson T51', category: 'Survey', serialNumber: 'TRT-2022-0013', location: 'Jebel Ali', lastCalibration: '2026-01-18', nextCalibration: '2026-07-18', status: 'calibrated' },
  { id: 'ast-038', name: 'Kongsberg EM2040P', category: 'Survey', serialNumber: 'KGE-2023-0002', location: 'Das Island', lastCalibration: '2026-03-22', nextCalibration: '2026-09-22', status: 'calibrated' },
  { id: 'ast-039', name: 'Sonardyne Scout', category: 'Survey', serialNumber: 'SNS-2021-0039', location: 'Jebel Ali', lastCalibration: '2025-12-08', nextCalibration: '2026-06-08', status: 'due-soon' },
  { id: 'ast-040', name: 'Valeport SWiFT CTD', category: 'Survey', serialNumber: 'VSW-2022-0025', location: 'Das Island', lastCalibration: '2026-02-14', nextCalibration: '2026-08-14', status: 'calibrated' },
  { id: 'ast-041', name: 'Trimble SPS855', category: 'Survey', serialNumber: 'TSP-2023-0010', location: 'Jebel Ali', lastCalibration: '2025-09-30', nextCalibration: '2026-03-30', status: 'overdue' },
  // Communication (4)
  { id: 'ast-042', name: 'Motorola DP4801e', category: 'Communication', serialNumber: 'MOD-2022-0021', location: 'Mussafah', lastCalibration: '2026-03-05', nextCalibration: '2026-09-05', status: 'calibrated' },
  { id: 'ast-043', name: 'Icom IC-M94D', category: 'Communication', serialNumber: 'ICM-2021-0037', location: 'Das Island', lastCalibration: '2025-11-12', nextCalibration: '2026-05-12', status: 'due-soon' },
  { id: 'ast-044', name: 'Hytera PD985', category: 'Communication', serialNumber: 'HYP-2023-0003', location: 'Jebel Ali', lastCalibration: '2026-01-28', nextCalibration: '2026-07-28', status: 'calibrated' },
  { id: 'ast-045', name: 'SAILOR 6222 VHF', category: 'Communication', serialNumber: 'SSV-2022-0017', location: 'Das Island', lastCalibration: '2025-10-15', nextCalibration: '2026-04-15', status: 'overdue' },
];

// ─── 8 Projects ───
const projects: Project[] = [
  { id: 'prj-001', name: 'ADNOC Pipeline Inspection', client: 'ADNOC', description: 'ROV inspection of subsea pipeline network', progress: 75, budgetSpent: 1900000, budgetTotal: 2500000, startDate: '2026-01-15', endDate: '2026-07-15', location: 'Offshore Abu Dhabi', team: 8, status: 'active' },
  { id: 'prj-002', name: 'ZADCO Platform Maintenance', client: 'ZADCO', description: 'Annual maintenance of offshore platforms', progress: 40, budgetSpent: 700000, budgetTotal: 1800000, startDate: '2026-03-01', endDate: '2026-09-30', location: 'Upper Zakum', team: 12, status: 'active' },
  { id: 'prj-003', name: 'Saudi Aramco Jacket Survey', client: 'Saudi Aramco', description: 'Structural integrity assessment of offshore jackets', progress: 20, budgetSpent: 400000, budgetTotal: 2000000, startDate: '2026-04-15', endDate: '2026-12-15', location: 'Offshore KSA', team: 6, status: 'planning' },
  { id: 'prj-004', name: 'QP Tank NDT Campaign', client: 'Qatar Petroleum', description: 'Ultrasonic and radiographic testing of storage tanks', progress: 60, budgetSpent: 850000, budgetTotal: 1400000, startDate: '2026-02-01', endDate: '2026-06-30', location: 'Ras Laffan', team: 5, status: 'active' },
  { id: 'prj-005', name: 'Borouge Cable Installation', client: 'Borouge', description: 'Subsea fiber optic cable laying', progress: 10, budgetSpent: 200000, budgetTotal: 1600000, startDate: '2026-05-10', endDate: '2026-11-10', location: 'Ruwais', team: 10, status: 'planning' },
  { id: 'prj-006', name: 'PDO Riser Inspection', client: 'PDO', description: 'ROV inspection of riser systems and anode survey', progress: 90, budgetSpent: 580000, budgetTotal: 650000, startDate: '2025-11-01', endDate: '2026-05-30', location: 'Offshore Oman', team: 4, status: 'active' },
  { id: 'prj-007', name: 'Dubai Petroleum FPSO', client: 'Dubai Petroleum', description: 'FPSO hull inspection and class survey', progress: 100, budgetSpent: 320000, budgetTotal: 320000, startDate: '2026-01-05', endDate: '2026-04-30', location: 'Fateh Field', team: 3, status: 'completed' },
  { id: 'prj-008', name: 'TAKREER Radio Upgrade', client: 'TAKREER', description: 'UHF communication system upgrade', progress: 30, budgetSpent: 45000, budgetTotal: 150000, startDate: '2026-04-20', endDate: '2026-06-20', location: 'Ruwais', team: 2, status: 'planning' },
];

// ─── 20 Stock Items ───
const stockItems: StockItem[] = [
  { id: 'stk-001', sku: 'ROV-CBL-001', name: 'ROV Umbilical Cable 200m', category: 'ROV Spares', quantity: 12, warehouse: 'Jebel Ali', reorderLevel: 5, unitCost: 8500, status: 'adequate' },
  { id: 'stk-002', sku: 'NDT-PRO-002', name: 'Ultrasonic Probe 5MHz', category: 'NDT Consumables', quantity: 45, warehouse: 'Mussafah', reorderLevel: 20, unitCost: 320, status: 'adequate' },
  { id: 'stk-003', sku: 'DIV-KIT-003', name: 'Dive Helmet Kirby Morgan', category: 'Diving Equipment', quantity: 3, warehouse: 'Das Island', reorderLevel: 4, unitCost: 12500, status: 'critical' },
  { id: 'stk-004', sku: 'CRN-PRT-004', name: 'Crane Wire Rope 30mm x 200m', category: 'Crane Spares', quantity: 8, warehouse: 'Jebel Ali', reorderLevel: 3, unitCost: 15600, status: 'adequate' },
  { id: 'stk-005', sku: 'COM-BAT-005', name: 'Radio Battery Pack Li-ion', category: 'Communication', quantity: 22, warehouse: 'Mussafah', reorderLevel: 15, unitCost: 180, status: 'adequate' },
  { id: 'stk-006', sku: 'SUR-TRN-006', name: 'Transponder Sonardyne', category: 'Survey Equipment', quantity: 6, warehouse: 'Das Island', reorderLevel: 4, unitCost: 42000, status: 'low' },
  { id: 'stk-007', sku: 'ROV-THR-007', name: 'ROV Thruster Tecnadyne 520', category: 'ROV Spares', quantity: 4, warehouse: 'Jebel Ali', reorderLevel: 3, unitCost: 28500, status: 'low' },
  { id: 'stk-008', sku: 'NDT-FIL-008', name: 'Radiographic Film 100ft', category: 'NDT Consumables', quantity: 18, warehouse: 'Mussafah', reorderLevel: 10, unitCost: 450, status: 'adequate' },
  { id: 'stk-009', sku: 'DIV-SUI-009', name: 'Drysuit Viking Pro 1000', category: 'Diving Equipment', quantity: 7, warehouse: 'Das Island', reorderLevel: 5, unitCost: 6800, status: 'adequate' },
  { id: 'stk-010', sku: 'CRN-HOO-010', name: 'Crane Hook Block 50T', category: 'Crane Spares', quantity: 2, warehouse: 'Jebel Ali', reorderLevel: 2, unitCost: 45000, status: 'low' },
  { id: 'stk-011', sku: 'COM-ANT-011', name: 'VHF Marine Antenna', category: 'Communication', quantity: 15, warehouse: 'Mussafah', reorderLevel: 8, unitCost: 290, status: 'adequate' },
  { id: 'stk-012', sku: 'SUR-CTD-012', name: 'CTD Sensor Valeport', category: 'Survey Equipment', quantity: 4, warehouse: 'Das Island', reorderLevel: 3, unitCost: 18500, status: 'low' },
  { id: 'stk-013', sku: 'ROV-CAM-013', name: 'ROV Camera HD 1080p', category: 'ROV Spares', quantity: 9, warehouse: 'Jebel Ali', reorderLevel: 4, unitCost: 12000, status: 'adequate' },
  { id: 'stk-014', sku: 'NDT-COU-014', name: 'Ultrasonic Couplant Gel 5L', category: 'NDT Consumables', quantity: 32, warehouse: 'Mussafah', reorderLevel: 12, unitCost: 65, status: 'adequate' },
  { id: 'stk-015', sku: 'DIV-REG-015', name: 'Dive Regulator Apeks TX50', category: 'Diving Equipment', quantity: 5, warehouse: 'Das Island', reorderLevel: 4, unitCost: 2400, status: 'low' },
  { id: 'stk-016', sku: 'CRN-SLI-016', name: 'Crane Sling 20T x 8m', category: 'Crane Spares', quantity: 14, warehouse: 'Jebel Ali', reorderLevel: 6, unitCost: 1800, status: 'adequate' },
  { id: 'stk-017', sku: 'COM-HDS-017', name: 'Noise-Cancelling Headset', category: 'Communication', quantity: 28, warehouse: 'Mussafah', reorderLevel: 10, unitCost: 350, status: 'adequate' },
  { id: 'stk-018', sku: 'SUR-GPS-018', name: 'GPS Receiver Trimble', category: 'Survey Equipment', quantity: 3, warehouse: 'Das Island', reorderLevel: 3, unitCost: 32000, status: 'critical' },
  { id: 'stk-019', sku: 'ROV-LIG-019', name: 'ROV LED Light Array', category: 'ROV Spares', quantity: 11, warehouse: 'Jebel Ali', reorderLevel: 5, unitCost: 5600, status: 'adequate' },
  { id: 'stk-020', sku: 'NDT-MAG-020', name: 'Magnetic Particle Yoke', category: 'NDT Consumables', quantity: 6, warehouse: 'Mussafah', reorderLevel: 4, unitCost: 2800, status: 'low' },
];

// ─── 6 Invoices (5% UAE VAT) ───
const invoices: Invoice[] = [
  { id: 'inv-001', number: 'INV-2026-001', client: 'ADNOC', issueDate: '2026-04-01', dueDate: '2026-05-01', subtotal: 450000, vat: 22500, total: 472500, status: 'paid' },
  { id: 'inv-002', number: 'INV-2026-002', client: 'ZADCO', issueDate: '2026-04-15', dueDate: '2026-05-15', subtotal: 180000, vat: 9000, total: 189000, status: 'pending' },
  { id: 'inv-003', number: 'INV-2026-003', client: 'Dubai Petroleum', issueDate: '2026-03-20', dueDate: '2026-04-20', subtotal: 320000, vat: 16000, total: 336000, status: 'paid' },
  { id: 'inv-004', number: 'INV-2026-004', client: 'Qatar Petroleum', issueDate: '2026-02-28', dueDate: '2026-03-30', subtotal: 195000, vat: 9750, total: 204750, status: 'overdue' },
  { id: 'inv-005', number: 'INV-2026-005', client: 'Borouge', issueDate: '2026-04-25', dueDate: '2026-05-25', subtotal: 89000, vat: 4450, total: 93450, status: 'draft' },
  { id: 'inv-006', number: 'INV-2026-006', client: 'PDO', issueDate: '2026-04-10', dueDate: '2026-05-10', subtotal: 550000, vat: 27500, total: 577500, status: 'pending' },
];

// ─── 8 Payments ───
const payments: Payment[] = [
  { id: 'pay-001', number: 'PAY-2026-001', date: '2026-04-05', client: 'ADNOC', amount: 472500, method: 'bank', reference: 'TT-ADNOC-450K', status: 'cleared' },
  { id: 'pay-002', number: 'PAY-2026-002', date: '2026-04-18', client: 'ZADCO', amount: 189000, method: 'bank', reference: 'TT-ZADCO-180K', status: 'pending' },
  { id: 'pay-003', number: 'PAY-2026-003', date: '2026-03-25', client: 'Dubai Petroleum', amount: 336000, method: 'bank', reference: 'TT-DP-320K', status: 'cleared' },
  { id: 'pay-004', number: 'PAY-2026-004', date: '2026-04-22', client: 'Qatar Petroleum', amount: 204750, method: 'cheque', reference: 'CH-QP-195K', status: 'pending' },
  { id: 'pay-005', number: 'PAY-2026-005', date: '2026-04-28', client: 'Borouge', amount: 93450, method: 'bank', reference: 'TT-BOR-89K', status: 'pending' },
  { id: 'pay-006', number: 'PAY-2026-006', date: '2026-04-12', client: 'Saudi Aramco', amount: 720000, method: 'bank', reference: 'TT-ARAMCO-720K', status: 'cleared' },
  { id: 'pay-007', number: 'PAY-2026-007', date: '2026-04-30', client: 'ADMA-OPCO', amount: 280000, method: 'cash', reference: 'CASH-ADMA-280K', status: 'cleared' },
  { id: 'pay-008', number: 'PAY-2026-008', date: '2026-05-01', client: 'Kuwait Oil Company', amount: 410000, method: 'bank', reference: 'TT-KOC-410K', status: 'pending' },
];

// ─── 8 Suppliers ───
const suppliers: Supplier[] = [
  { id: 'sup-001', name: 'Teledyne Marine FZE', category: 'ROV Equipment', email: 'sales@teledynemarine.ae', phone: '+971 4 815 5000', address: 'Dubai Silicon Oasis, Dubai', rating: 5, paymentTerms: 'Net 30' },
  { id: 'sup-002', name: 'Baker Hughes Middle East', category: 'NDT Equipment', email: 'orders@bakerhughes.ae', phone: '+971 2 555 8000', address: 'Corniche Road, Abu Dhabi', rating: 4, paymentTerms: 'Net 45' },
  { id: 'sup-003', name: 'Liebherr Gulf FZE', category: 'Crane Equipment', email: 'gulf@liebherr.com', phone: '+971 4 880 5100', address: 'Jebel Ali Free Zone, Dubai', rating: 5, paymentTerms: 'Net 60' },
  { id: 'sup-004', name: 'Kirby Morgan Middle East', category: 'Diving Equipment', email: 'me@kirbymorgan.ae', phone: '+971 2 644 2200', address: 'Mussafah Industrial Area, Abu Dhabi', rating: 4, paymentTerms: 'Net 30' },
  { id: 'sup-005', name: 'Sonardyne Asia', category: 'Survey Equipment', email: 'asia@sonardyne.com', phone: '+971 4 390 2700', address: 'Dubai Airport Free Zone, Dubai', rating: 5, paymentTerms: 'Net 45' },
  { id: 'sup-006', name: 'Motorola Solutions UAE', category: 'Communication', email: 'uae@motorolasolutions.com', phone: '+971 4 374 0000', address: 'Sheikh Zayed Road, Dubai', rating: 3, paymentTerms: 'Net 30' },
  { id: 'sup-007', name: 'Kongsberg Maritime', category: 'Survey Equipment', email: 'km@kongsberg.ae', phone: '+971 4 803 5600', address: 'Hamriyah Free Zone, Sharjah', rating: 5, paymentTerms: 'Net 60' },
  { id: 'sup-008', name: 'Desert Diving Supply', category: 'Diving Equipment', email: 'info@desertdiving.ae', phone: '+971 2 555 3300', address: 'Mina Port, Abu Dhabi', rating: 3, paymentTerms: 'Cash on Delivery' },
];

// ─── 6 Purchase Orders ───
const purchaseOrders: PurchaseOrder[] = [
  { id: 'po-001', number: 'PO-2026-001', supplier: 'Teledyne Marine FZE', date: '2026-04-01', deliveryDate: '2026-05-15', items: 5, total: 125000, status: 'approved' },
  { id: 'po-002', number: 'PO-2026-002', supplier: 'Baker Hughes Middle East', date: '2026-04-10', deliveryDate: '2026-05-10', items: 12, total: 48000, status: 'received' },
  { id: 'po-003', number: 'PO-2026-003', supplier: 'Liebherr Gulf FZE', date: '2026-04-15', deliveryDate: '2026-06-01', items: 3, total: 210000, status: 'pending' },
  { id: 'po-004', number: 'PO-2026-004', supplier: 'Kirby Morgan Middle East', date: '2026-04-20', deliveryDate: '2026-05-05', items: 4, total: 56000, status: 'approved' },
  { id: 'po-005', number: 'PO-2026-005', supplier: 'Sonardyne Asia', date: '2026-04-25', deliveryDate: '2026-06-15', items: 2, total: 95000, status: 'pending' },
  { id: 'po-006', number: 'PO-2026-006', supplier: 'Motorola Solutions UAE', date: '2026-04-28', deliveryDate: '2026-05-20', items: 20, total: 15000, status: 'pending' },
];

// ─── 4 Workflows ───
const workflows: Workflow[] = [
  { id: 'wf-001', name: 'Enquiry Approval', description: 'Route new enquiries to sales manager for qualification', nodes: 5, runs: 128, status: 'active' },
  { id: 'wf-002', name: 'Invoice Generation', description: 'Auto-generate invoices on project milestones', nodes: 8, runs: 342, status: 'active' },
  { id: 'wf-003', name: 'Certification Alert', description: 'Notify when personnel certifications are expiring', nodes: 4, runs: 56, status: 'active' },
  { id: 'wf-004', name: 'Stock Reorder', description: 'Create PO when inventory falls below reorder level', nodes: 6, runs: 89, status: 'paused' },
];

// ─── 4 Personas ───
const personas: Persona[] = [
  { id: 'sales-assistant', name: 'Sales Assistant', description: 'Helps with enquiries, proposals, and client communication', tools: ['/generate_form', '/create_dashboard', '/summarize'], tone: 'Professional and friendly', systemPrompt: 'You are a sales assistant for Aries Marine. Help the team manage enquiries, create proposals, and track deals.' },
  { id: 'operations-expert', name: 'Operations Expert', description: 'Manages projects, personnel, and asset scheduling', tools: ['/generate_form', '/summarize', '/export'], tone: 'Technical and precise', systemPrompt: 'You are an operations expert for Aries Marine. Help with project planning, resource allocation, and compliance.' },
  { id: 'finance-manager', name: 'Finance Manager', description: 'Handles invoicing, payments, and financial reporting', tools: ['/create_dashboard', '/export', '/summarize'], tone: 'Formal and analytical', systemPrompt: 'You are a finance manager for Aries Marine. Help generate invoices, track payments, and create financial reports.' },
  { id: 'hr-coordinator', name: 'HR Coordinator', description: 'Manages personnel, certifications, and compliance', tools: ['/generate_form', '/summarize'], tone: 'Supportive and organized', systemPrompt: 'You are an HR coordinator for Aries Marine. Help track certifications, manage personnel records, and ensure compliance.' },
];

// ─── 5 Channels ───
const channels: Channel[] = [
  { id: 'ch-001', name: 'Email Inbox', type: 'email', description: 'Primary company email for client enquiries', status: 'connected', lastSync: '2026-05-05T09:30:00Z', messagesToday: 24 },
  { id: 'ch-002', name: 'WhatsApp Business', type: 'whatsapp', description: 'Client communication via WhatsApp', status: 'connected', lastSync: '2026-05-05T10:15:00Z', messagesToday: 18 },
  { id: 'ch-003', name: 'Microsoft Teams', type: 'teams', description: 'Internal team collaboration', status: 'connected', lastSync: '2026-05-05T08:45:00Z', messagesToday: 56 },
  { id: 'ch-004', name: 'Slack', type: 'slack', description: 'Developer and operations chat', status: 'disconnected', lastSync: '2026-05-04T16:20:00Z', messagesToday: 0 },
  { id: 'ch-005', name: 'Telegram', type: 'telegram', description: 'Field crew communication', status: 'error', lastSync: '2026-05-03T11:00:00Z', messagesToday: 3 },
];

// ─── 6 Wiki Pages ───
const wikiPages: WikiPage[] = [
  { id: 'wiki-001', title: 'BOSIET Certification Guide', category: 'Training', author: 'Aisha Bello', lastEdited: '2026-04-15', content: '# BOSIET Certification Guide\n\n## Overview\nBOSIET (Basic Offshore Safety Induction and Emergency Training) is required for all offshore personnel.\n\n## Requirements\n- Valid passport\n- Medical fitness certificate\n- Swimming ability\n\n## Renewal\nBOSIET is valid for 4 years. Renewal must be completed before expiry.', tags: ['training', 'safety', 'offshore'] },
  { id: 'wiki-002', title: 'ROV Operating Procedures', category: 'Operations', author: 'Omar Hassan', lastEdited: '2026-03-28', content: '# ROV Operating Procedures\n\n## Pre-Dive Checklist\n1. Visual inspection of tether\n2. Camera and lighting test\n3. Thruster function check\n4. Communication test with surface\n\n## Depth Limits\n- Falcon DR: 300m\n- Tiger: 500m\n- XLT-30: 1000m', tags: ['rov', 'operations', 'checklist'] },
  { id: 'wiki-003', title: 'NDT Inspection Standards', category: 'Inspection', author: 'Lisa Chen', lastEdited: '2026-04-22', content: '# NDT Inspection Standards\n\n## Methods\n- Ultrasonic Testing (UT)\n- Radiographic Testing (RT)\n- Magnetic Particle (MT)\n- Liquid Penetrant (PT)\n\n## Acceptance Criteria\nPer ASME V and client specifications.', tags: ['ndt', 'inspection', 'standards'] },
  { id: 'wiki-004', title: 'Crane Safety Protocol', category: 'Safety', author: 'James Wilson', lastEdited: '2026-02-10', content: '# Crane Safety Protocol\n\n## Daily Checks\n- Wire rope condition\n- Load chart verification\n- Outrigger positioning\n- Radio communication test\n\n## Lift Categories\n- Ordinary: < 75% capacity\n- Critical: > 75% capacity\n- Engineered: Non-routine', tags: ['crane', 'safety', 'lifting'] },
  { id: 'wiki-005', title: 'UAE VAT Guidelines', category: 'Finance', author: 'Fatima Al-Zahra', lastEdited: '2026-01-20', content: '# UAE VAT Guidelines\n\n## Rate\n5% on all taxable supplies\n\n## Invoicing\n- TRN must be shown\n- VAT-exclusive and inclusive amounts\n- Quarterly filing\n\n## Exemptions\n- Export of services outside GCC\n- Residential property leases', tags: ['vat', 'finance', 'uae'] },
  { id: 'wiki-006', title: 'Diving Emergency Response', category: 'Safety', author: 'Rashid Khan', lastEdited: '2026-04-01', content: '# Diving Emergency Response\n\n## Emergency Types\n- Decompression sickness (DCS)\n- Barotrauma\n- Entrapment\n- Equipment failure\n\n## Response Procedures\n1. Abort dive immediately\n2. Initiate first aid\n3. Contact Diving Supervisor\n4. Prepare hyperbaric chamber', tags: ['diving', 'emergency', 'safety'] },
];

// ─── 8 Dashboard KPI Metrics ───
const dashboardMetrics: DashboardMetric[] = [
  { label: 'Open Enquiries', value: 6, change: 12, changeType: 'increase', icon: 'Inbox', prefix: '', suffix: '' },
  { label: 'Active Projects', value: 4, change: 0, changeType: 'increase', icon: 'FolderKanban', prefix: '', suffix: '' },
  { label: 'Personnel Offshore', value: 2, change: -1, changeType: 'decrease', icon: 'Users', prefix: '', suffix: '' },
  { label: 'Monthly Revenue', value: 2.4, change: 18, changeType: 'increase', icon: 'DollarSign', prefix: 'AED ', suffix: 'M' },
  { label: 'Pending Invoices', value: 3, change: 1, changeType: 'increase', icon: 'FileText', prefix: '', suffix: '' },
  { label: 'Low Stock Items', value: 7, change: -2, changeType: 'decrease', icon: 'Package', prefix: '', suffix: '' },
  { label: 'Upcoming Calibrations', value: 12, change: 3, changeType: 'increase', icon: 'Wrench', prefix: '', suffix: '' },
  { label: 'Expiring Certifications', value: 3, change: 1, changeType: 'increase', icon: 'AlertTriangle', prefix: '', suffix: '' },
];

// ─── 6 Notifications ───
const notifications: Notification[] = [
  { id: 'notif-001', message: 'New enquiry from ADNOC', time: '2 min ago', read: false, type: 'info' },
  { id: 'notif-002', message: 'BOSIET cert expires in 12 days', time: '1 hour ago', read: false, type: 'warning' },
  { id: 'notif-003', message: 'Invoice INV-004 is overdue', time: '3 hours ago', read: false, type: 'error' },
  { id: 'notif-004', message: 'Project "Pipeline Insp" milestone reached', time: '5 hours ago', read: true, type: 'success' },
  { id: 'notif-005', message: 'Purchase Order PO-002 approved', time: '1 day ago', read: true, type: 'success' },
  { id: 'notif-006', message: 'New comment on Wiki page', time: '2 days ago', read: true, type: 'info' },
];

// ─── 4 Dynamic UIs ───
const dynamicUIs: DynamicUI[] = [
  { id: 'ui-001', type: 'dashboard', title: 'Sales Pipeline View', description: 'AI-generated sales dashboard with enquiry funnel', config: { columns: ['New', 'Qualified', 'Proposal', 'Negotiation', 'Approved'], filters: ['dateRange', 'assignedTo'] } },
  { id: 'ui-002', type: 'form', title: 'Enquiry Capture Form', description: 'Quick capture form for new client enquiries', config: { fields: ['client', 'contact', 'service', 'value', 'description'], layout: 'two-column' } },
  { id: 'ui-003', type: 'kanban', title: 'Project Task Board', description: 'Kanban board for tracking project deliverables', config: { swimlanes: ['Backlog', 'In Progress', 'Review', 'Done'], groupBy: 'assignee' } },
  { id: 'ui-004', type: 'report', title: 'Monthly Financial Summary', description: 'Revenue and expense summary with charts', config: { period: 'monthly', charts: ['revenue', 'expenses', 'profit'], format: 'pdf' } },
];

// ─── 4 RAG Documents ───
const ragDocuments: RagDocument[] = [
  { id: 'rag-001', name: 'Company Handbook 2026.pdf', type: 'pdf', size: '4.2 MB', status: 'indexed', indexedAt: '2026-04-01T10:00:00Z' },
  { id: 'rag-002', name: 'ADNOC Contract Terms.pdf', type: 'pdf', size: '8.7 MB', status: 'indexed', indexedAt: '2026-04-05T14:30:00Z' },
  { id: 'rag-003', name: 'Equipment Manuals.doc', type: 'doc', size: '12.3 MB', status: 'pending' },
  { id: 'rag-004', name: 'Safety Procedures.txt', type: 'txt', size: '1.1 MB', status: 'failed' },
];

// ─── Export Functions ───
export const getEnquiries = (): Enquiry[] => enquiries;
export const getEnquiryById = (id: string): Enquiry | undefined => enquiries.find(e => e.id === id);
export const getPersonnel = (): Personnel[] => personnel;
export const getAssets = (): Asset[] => assets;
export const getProjects = (): Project[] => projects;
export const getStock = (): StockItem[] => stockItems;
export const getInvoices = (): Invoice[] => invoices;
export const getPayments = (): Payment[] => payments;
export const getSuppliers = (): Supplier[] => suppliers;
export const getPurchaseOrders = (): PurchaseOrder[] => purchaseOrders;
export const getWorkflows = (): Workflow[] => workflows;
export const getPersonas = (): Persona[] => personas;
export const getChannels = (): Channel[] => channels;
export const getWikiPages = (): WikiPage[] => wikiPages;
export const getWikiById = (id: string): WikiPage | undefined => wikiPages.find(w => w.id === id);
export const getDashboardMetrics = (): DashboardMetric[] => dashboardMetrics;
export const getNotifications = (): Notification[] => notifications;
export const getDynamicUIs = (): DynamicUI[] => dynamicUIs;
export const getDynamicUIById = (id: string): DynamicUI | undefined => dynamicUIs.find(u => u.id === id);
export const getRagDocuments = (): RagDocument[] => ragDocuments;
