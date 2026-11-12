"""Known schools: what the student types (a name, an abbreviation, a web domain) becomes the Blackboard address.

The settings forms accept ``King Saud University``, ``KSU`` or ``ksu.edu.sa`` as well as a full address;
``normalize_base_url`` asks ``resolve`` first. Only addresses that answered Blackboard's public
``/learn/api/public/v1/system/version`` check (``scripts/verify-schools.py``) belong in ``SCHOOLS``,
each with the date it was checked.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class School:
    name: str  # English name, shown in lists
    url: str  # https://host, the Blackboard address
    domain: str  # the school's own web domain, which students know best
    country: str  # ISO 3166-1 alpha-2
    local_names: tuple[str, ...] = ()  # the name in the local language; matched, never shown
    aliases: tuple[str, ...] = ()  # abbreviations; matched, never shown
    verified: str = ""  # the day the address answered the Blackboard check


SCHOOLS: tuple[School, ...] = (
    School("Istanbul Health and Technology University", "https://blackboard.istun.edu.tr", "istun.edu.tr", "TR",
           ("İstanbul Sağlık ve Teknoloji Üniversitesi",), ("ISTUN",), "2026-11-07"),
    School("King Saud University", "https://lms.ksu.edu.sa", "ksu.edu.sa", "SA",
           ("جامعة الملك سعود",), ("KSU",), "2026-11-07"),
    School("Saudi Electronic University", "https://lms.seu.edu.sa", "seu.edu.sa", "SA",
           ("الجامعة السعودية الإلكترونية",), ("SEU",), "2026-11-07"),
    School("King Fahd University of Petroleum and Minerals", "https://blackboard.kfupm.edu.sa", "kfupm.edu.sa", "SA",
           ("جامعة الملك فهد للبترول والمعادن",), ("KFUPM",), "2026-11-07"),
    School("Imam Mohammad Ibn Saud Islamic University", "https://lms.imamu.edu.sa", "imamu.edu.sa", "SA",
           ("جامعة الإمام محمد بن سعود الإسلامية",), ("IMSIU", "IMAMU"), "2026-11-07"),
    School("Umm Al-Qura University", "https://lms.uqu.edu.sa", "uqu.edu.sa", "SA",
           ("جامعة أم القرى",), ("UQU",), "2026-11-07"),
    School("King Abdulaziz University", "https://lms.kau.edu.sa", "kau.edu.sa", "SA",
           ("جامعة الملك عبدالعزيز",), ("KAU",), "2026-11-07"),
    School("Qassim University", "https://lms.qu.edu.sa", "qu.edu.sa", "SA",
           ("جامعة القصيم",), (), "2026-11-07"),
    School("King Khalid University", "https://lms.kku.edu.sa", "kku.edu.sa", "SA",
           ("جامعة الملك خالد",), ("KKU",), "2026-11-07"),
    School("Taif University", "https://lms.tu.edu.sa", "tu.edu.sa", "SA",
           ("جامعة الطائف",), (), "2026-11-07"),
    School("Northern Border University", "https://lms.nbu.edu.sa", "nbu.edu.sa", "SA",
           ("جامعة الحدود الشمالية",), ("NBU",), "2026-11-07"),
    School("Prince Sattam bin Abdulaziz University", "https://lms.psau.edu.sa", "psau.edu.sa", "SA",
           ("جامعة الأمير سطام بن عبدالعزيز",), ("PSAU",), "2026-11-07"),
    School("King Faisal University", "https://lms.kfu.edu.sa", "kfu.edu.sa", "SA",
           ("جامعة الملك فيصل",), ("KFU",), "2026-11-07"),
    School("Taibah University", "https://lms.taibahu.edu.sa", "taibahu.edu.sa", "SA",
           ("جامعة طيبة",), (), "2026-11-07"),
    School("University of Jeddah", "https://lms.ju.edu.sa", "ju.edu.sa", "SA",
           ("جامعة جدة",), (), "2026-11-07"),
    School("Jazan University", "https://lms.jazanu.edu.sa", "jazanu.edu.sa", "SA",
           ("جامعة جازان",), (), "2026-11-07"),
    # AE
    School("Abu Dhabi University", "https://blackboard.adu.ac.ae", "adu.ac.ae", "AE",
           ("جامعة أبوظبي",), ("ADU",), "2026-11-08"),
    School("American University of Sharjah", "https://ilearn.aus.edu", "aus.edu", "AE",
           ("الجامعة الأمريكية في الشارقة",), ("AUS",), "2026-11-08"),
    School("Khalifa University", "https://elearn.ku.ac.ae", "ku.ac.ae", "AE",
           ("جامعة خليفة",), ("KUSTAR",), "2026-11-08"),
    School("The British University in Dubai", "https://blackboard.buid.ac.ae", "buid.ac.ae", "AE",
           ("الجامعة البريطانية في دبي",), ("BUiD",), "2026-11-08"),
    School("University of Sharjah", "https://elearning.sharjah.ac.ae", "sharjah.ac.ae", "AE",
           ("جامعة الشارقة",), ("UOS",), "2026-11-08"),
    # AU
    School("Bond University", "https://ilearn.bond.edu.au", "bond.edu.au", "AU",
           (), ("BOND",), "2026-11-08"),
    School("Curtin University", "https://lms.curtin.edu.au", "curtin.edu.au", "AU",
           (), ("CURTIN",), "2026-11-08"),
    School("James Cook University", "https://learn.jcu.edu.au", "jcu.edu.au", "AU",
           (), ("JCU",), "2026-11-08"),
    School("Southern Cross University", "https://learn.scu.edu.au", "scu.edu.au", "AU",
           (), ("SCU",), "2026-11-08"),
    School("The University of Notre Dame Australia", "https://learnit.nd.edu.au", "nd.edu.au", "AU",
           (), ("UNDA", "NDA", "nd.edu.au", "notredame.edu.au"), "2026-11-08"),
    School("The University of Queensland", "https://learn.uq.edu.au", "uq.edu.au", "AU",
           (), ("UQ",), "2026-11-08"),
    School("Torrens University Australia", "https://torrens.blackboard.com", "torrens.edu.au", "AU",
           (), ("TUA",), "2026-11-08"),
    # BE
    School("University of Antwerp", "https://blackboard.uantwerpen.be", "uantwerpen.be", "BE",
           ("Universiteit Antwerpen",), ("UAntwerpen", "UA"), "2026-11-08"),
    # BH
    School("University of Bahrain", "https://blackboard.uob.edu.bh", "uob.edu.bh", "BH",
           ("جامعة البحرين",), ("UOB",), "2026-11-08"),
    # BR
    School("Insper Institute of Education and Research", "https://insper.blackboard.com", "insper.edu.br", "BR",
           ("Insper Instituto de Ensino e Pesquisa",), ("INSPER",), "2026-11-08"),
    School("La Salle University Brazil", "https://lex.lasalle.edu.br", "lasalle.edu.br", "BR",
           ("Universidade La Salle",), ("UNILASALLE", "lasalle.edu.br", "unilasalle.edu.br"), "2026-11-08"),
    # CA
    School("Humber Polytechnic", "https://learn.humber.ca", "humber.ca", "CA",
           ("Humber College",), ("HUMBER",), "2026-11-08"),
    School("Seneca Polytechnic", "https://learn.senecapolytechnic.ca", "senecapolytechnic.ca", "CA",
           ("Seneca College",), ("SENECA",), "2026-11-08"),
    # CL
    School("Duoc UC", "https://ava.duoc.cl", "duoc.cl", "CL",
           ("Instituto Profesional Duoc UC",), ("DUOC",), "2026-11-08"),
    School("Mayor University", "https://umayor.blackboard.com", "umayor.cl", "CL",
           ("Universidad Mayor",), ("UMAYOR",), "2026-11-08"),
    School("San Sebastian University", "https://uss.blackboard.com", "uss.cl", "CL",
           ("Universidad San Sebastián",), ("USS",), "2026-11-08"),
    # CN
    School("The Chinese University of Hong Kong, Shenzhen", "https://bb.cuhk.edu.cn", "cuhk.edu.cn", "CN",
           ("香港中文大学（深圳）",), ("CUHK-Shenzhen", "CUHKSZ"), "2026-11-08"),
    # CY
    School("University of Nicosia", "https://learn.unic.ac.cy", "unic.ac.cy", "CY",
           ("Πανεπιστήμιο Λευκωσίας",), ("UNIC",), "2026-11-08"),
    # DO
    School("Universidad Iberoamericana", "https://unibe.blackboard.com", "unibe.edu.do", "DO",
           (), ("UNIBE",), "2026-11-08"),
    School("University of the Caribbean", "https://blackboard.unicaribe.edu.do", "unicaribe.edu.do", "DO",
           ("Universidad del Caribe",), ("UNICARIBE",), "2026-11-08"),
    # EC
    School("ECOTEC Technological University", "https://ecotec.blackboard.com", "ecotec.edu.ec", "EC",
           ("Universidad Tecnológica ECOTEC",), ("ECOTEC",), "2026-11-08"),
    School("Espiritu Santo University", "https://uees.blackboard.com", "uees.edu.ec", "EC",
           ("Universidad Espíritu Santo",), ("UEES",), "2026-11-08"),
    # EG
    School("Pharos University in Alexandria", "https://blackboard.pua.edu.eg", "pua.edu.eg", "EG",
           ("جامعة فاروس بالإسكندرية",), ("PUA",), "2026-11-08"),
    # ES
    School("Pablo de Olavide University", "https://campusvirtual.upo.es", "upo.es", "ES",
           ("Universidad Pablo de Olavide",), ("UPO",), "2026-11-08"),
    School("University of Navarra", "https://unav.blackboard.com", "unav.edu", "ES",
           ("Universidad de Navarra",), ("UNAV",), "2026-11-08"),
    School("University of Seville", "https://ev.us.es", "us.es", "ES",
           ("Universidad de Sevilla",), ("US",), "2026-11-08"),
    # GB
    School("Aberystwyth University", "https://blackboard.aber.ac.uk", "aber.ac.uk", "GB",
           ("Prifysgol Aberystwyth",), ("ABER",), "2026-11-08"),
    School("Aston University", "https://vle.aston.ac.uk", "aston.ac.uk", "GB",
           (), ("ASTON",), "2026-11-08"),
    School("Bangor University", "https://blackboard.bangor.ac.uk", "bangor.ac.uk", "GB",
           ("Prifysgol Bangor",), ("BANGOR",), "2026-11-08"),
    School("Cardiff University", "https://learningcentral.cf.ac.uk", "cf.ac.uk", "GB",
           ("Prifysgol Caerdydd",), ("CU", "cf.ac.uk", "cardiff.ac.uk"), "2026-11-08"),
    School("Durham University", "https://blackboard.durham.ac.uk", "durham.ac.uk", "GB",
           (), ("DU",), "2026-11-08"),
    School("Edge Hill University", "https://learningedge.edgehill.ac.uk", "edgehill.ac.uk", "GB",
           (), ("EHU",), "2026-11-08"),
    School("Imperial College London", "https://bb.imperial.ac.uk", "imperial.ac.uk", "GB",
           (), ("ICL",), "2026-11-08"),
    School("Northumbria University", "https://elp.northumbria.ac.uk", "northumbria.ac.uk", "GB",
           (), ("UNN", "NORTHUMBRIA"), "2026-11-08"),
    School("Sheffield Hallam University", "https://shuspace.shu.ac.uk", "shu.ac.uk", "GB",
           (), ("SHU",), "2026-11-08"),
    School("Ulster University", "https://learning.ulster.ac.uk", "ulster.ac.uk", "GB",
           (), ("UU",), "2026-11-08"),
    School("University of Aberdeen", "https://abdn.blackboard.com", "abdn.ac.uk", "GB",
           (), ("ABDN",), "2026-11-08"),
    School("University of Bedfordshire", "https://breo.beds.ac.uk", "beds.ac.uk", "GB",
           (), ("BEDS", "BREO"), "2026-11-08"),
    School("University of Bristol", "https://www.ole.bris.ac.uk", "bris.ac.uk", "GB",
           (), ("BRISTOL", "BRIS", "bris.ac.uk", "bristol.ac.uk"), "2026-11-08"),
    School("University of Dundee", "https://my.dundee.ac.uk", "dundee.ac.uk", "GB",
           (), ("UOD",), "2026-11-08"),
    School("University of Leicester", "https://blackboard.le.ac.uk", "le.ac.uk", "GB",
           (), ("UOL",), "2026-11-08"),
    School("University of Lincoln", "https://blackboard.lincoln.ac.uk", "lincoln.ac.uk", "GB",
           (), ("LINCOLN",), "2026-11-08"),
    School("University of Reading", "https://www.bb.reading.ac.uk", "reading.ac.uk", "GB",
           (), ("UOR",), "2026-11-08"),
    School("University of Salford", "https://blackboard.salford.ac.uk", "salford.ac.uk", "GB",
           (), ("SALFORD",), "2026-11-08"),
    School("University of Sheffield", "https://vle.shef.ac.uk", "shef.ac.uk", "GB",
           (), ("SHEF", "SHEFFIELD", "shef.ac.uk", "sheffield.ac.uk"), "2026-11-08"),
    School("University of Southampton", "https://blackboard.soton.ac.uk", "soton.ac.uk", "GB",
           (), ("SOTON", "soton.ac.uk", "southampton.ac.uk"), "2026-11-08"),
    School("University of Staffordshire", "https://blackboard.staffs.ac.uk", "staffs.ac.uk", "GB",
           ("Staffordshire University",), ("STAFFS",), "2026-11-08"),
    School("University of the West of England", "https://blackboard.uwe.ac.uk", "uwe.ac.uk", "GB",
           (), ("UWE", "UWE Bristol"), "2026-11-08"),
    School("University of Westminster", "https://learning.westminster.ac.uk", "westminster.ac.uk", "GB",
           (), ("UOW",), "2026-11-08"),
    School("University of York", "https://vle.york.ac.uk", "york.ac.uk", "GB",
           (), ("UOY",), "2026-11-08"),
    # HK
    School("The Chinese University of Hong Kong", "https://blackboard.cuhk.edu.hk", "cuhk.edu.hk", "HK",
           ("香港中文大學",), ("CUHK",), "2026-11-08"),
    School("The Hong Kong Polytechnic University", "https://learn.polyu.edu.hk", "polyu.edu.hk", "HK",
           ("香港理工大學",), ("PolyU",), "2026-11-08"),
    # IE
    School("Trinity College Dublin", "https://mymodule.tcd.ie", "tcd.ie", "IE",
           ("Coláiste na Tríonóide, Baile Átha Cliath",), ("TCD",), "2026-11-08"),
    # IT
    School("Catholic University of the Sacred Heart", "https://blackboard.unicatt.it", "unicatt.it", "IT",
           ("Università Cattolica del Sacro Cuore",), ("UNICATT", "UCSC"), "2026-11-08"),
    School("Vita-Salute San Raffaele University", "https://bb.unisr.it", "unisr.it", "IT",
           ("Università Vita-Salute San Raffaele",), ("UniSR",), "2026-11-08"),
    # JP
    School("Osaka University", "https://www.cle.osaka-u.ac.jp", "osaka-u.ac.jp", "JP",
           ("大阪大学",), ("OU", "Handai"), "2026-11-08"),
    # KE
    School("United States International University Africa", "https://usiu.blackboard.com", "usiu.ac.ke", "KE",
           ("USIU-Africa",), ("USIU",), "2026-11-08"),
    # LB
    School("Lebanese American University", "https://elearn.lau.edu.lb", "lau.edu.lb", "LB",
           ("الجامعة اللبنانية الأميركية",), ("LAU",), "2026-11-08"),
    School("Notre Dame University-Louaize", "https://bb.ndu.edu.lb", "ndu.edu.lb", "LB",
           ("جامعة سيدة اللويزة",), ("NDU",), "2026-11-08"),
    # MX
    School("CETYS University", "https://cetys.blackboard.com", "cetys.mx", "MX",
           ("CETYS Universidad", "Centro de Enseñanza Técnica y Superior"), ("CETYS",), "2026-11-08"),
    School("Panamerican University", "https://blackboard.up.edu.mx", "up.edu.mx", "MX",
           ("Universidad Panamericana",), ("UP",), "2026-11-08"),
    School("University of Monterrey", "https://cursos-udem.blackboard.com", "udem.edu.mx", "MX",
           ("Universidad de Monterrey",), ("UDEM",), "2026-11-08"),
    School("University of the Valley of Mexico", "https://uvm.blackboard.com", "uvm.mx", "MX",
           ("Universidad del Valle de México",), ("UVM",), "2026-11-08"),
    # MY
    School("Sunway University", "https://elearn.sunway.edu.my", "sunway.edu.my", "MY",
           ("Universiti Sunway",), ("SUNWAY",), "2026-11-08"),
    # NL
    School("NHL Stenden University of Applied Sciences", "https://blackboard.nhlstenden.com", "nhlstenden.com", "NL",
           ("NHL Stenden Hogeschool",), ("NHL Stenden",), "2026-11-08"),
    # NZ
    School("University of Otago", "https://blackboard.otago.ac.nz", "otago.ac.nz", "NZ",
           ("Ōtākou Whakaihu Waka",), ("OTAGO",), "2026-11-08"),
    # PE
    School("Cesar Vallejo University", "https://ucv.blackboard.com", "ucv.edu.pe", "PE",
           ("Universidad César Vallejo",), ("UCV",), "2026-11-08"),
    School("Peruvian University of Applied Sciences", "https://aulavirtual.upc.edu.pe", "upc.edu.pe", "PE",
           ("Universidad Peruana de Ciencias Aplicadas",), ("UPC",), "2026-11-08"),
    School("Private University of the North", "https://upn.blackboard.com", "upn.edu.pe", "PE",
           ("Universidad Privada del Norte",), ("UPN",), "2026-11-08"),
    School("University of Lima", "https://ulima.blackboard.com", "ulima.edu.pe", "PE",
           ("Universidad de Lima",), ("ULIMA",), "2026-11-08"),
    School("University of the Pacific", "https://upacifico.blackboard.com", "up.edu.pe", "PE",
           ("Universidad del Pacífico",), ("UPACIFICO",), "2026-11-08"),
    # PH
    School("Mapua University", "https://mapua.blackboard.com", "mapua.edu.ph", "PH",
           (), ("MAPUA",), "2026-11-08"),
    # QA
    School("Qatar University", "https://elearning.qu.edu.qa", "qu.edu.qa", "QA",
           ("جامعة قطر",), ("QU",), "2026-11-08"),
    # SA
    School("Al-Baha University", "https://lms.bu.edu.sa", "bu.edu.sa", "SA",
           ("جامعة الباحة",), ("ABU",), "2026-11-08"),
    School("Dar Al-Hekma University", "https://elearning.dah.edu.sa", "dah.edu.sa", "SA",
           ("جامعة دار الحكمة",), ("DAH",), "2026-11-08"),
    School("Effat University", "https://blackboard.effatuniversity.edu.sa", "effatuniversity.edu.sa", "SA",
           ("جامعة عفت",), ("EFFAT",), "2026-11-08"),
    School("Imam Abdulrahman Bin Faisal University", "https://vle.iau.edu.sa", "iau.edu.sa", "SA",
           ("جامعة الإمام عبدالرحمن بن فيصل",), ("IAU",), "2026-11-08"),
    School("King Abdullah University of Science and Technology", "https://blackboard.kaust.edu.sa", "kaust.edu.sa", "SA",
           ("جامعة الملك عبدالله للعلوم والتقنية",), ("KAUST",), "2026-11-08"),
    School("King Saud bin Abdulaziz University for Health Sciences", "https://lms.ksau-hs.edu.sa", "ksau-hs.edu.sa", "SA",
           ("جامعة الملك سعود بن عبدالعزيز للعلوم الصحية",), ("KSAU-HS", "KSAUHS"), "2026-11-08"),
    School("Majmaah University", "https://lms.mu.edu.sa", "mu.edu.sa", "SA",
           ("جامعة المجمعة",), ("MU",), "2026-11-08"),
    School("Shaqra University", "https://lms.su.edu.sa", "su.edu.sa", "SA",
           ("جامعة شقراء",), ("SU",), "2026-11-08"),
    School("University of Bisha", "https://lms.ub.edu.sa", "ub.edu.sa", "SA",
           ("جامعة بيشة",), ("UB",), "2026-11-08"),
    School("University of Hafr Al-Batin", "https://lms.uhb.edu.sa", "uhb.edu.sa", "SA",
           ("جامعة حفر الباطن",), ("UHB",), "2026-11-08"),
    School("University of Hail", "https://uoh.blackboard.com", "uoh.edu.sa", "SA",
           ("جامعة حائل",), ("UOH",), "2026-11-08"),
    School("University of Tabuk", "https://lms.ut.edu.sa", "ut.edu.sa", "SA",
           ("جامعة تبوك",), ("UT",), "2026-11-08"),
    # SG
    School("SingHealth Academy", "https://elearn.singhealthacademy.edu.sg", "singhealthacademy.edu.sg", "SG",
           (), ("SingHealth",), "2026-11-08"),
    # TR
    School("Fenerbahce University", "https://blackboard.fbu.edu.tr", "fbu.edu.tr", "TR",
           ("Fenerbahçe Üniversitesi",), ("FBU", "FBÜ"), "2026-11-08"),
    School("Istanbul Okan University", "https://olearn.okan.edu.tr", "okan.edu.tr", "TR",
           ("İstanbul Okan Üniversitesi",), ("OKAN",), "2026-11-08"),
    School("Istinye University", "https://istinye.blackboard.com", "istinye.edu.tr", "TR",
           ("İstinye Üniversitesi",), ("ISU", "İSÜ"), "2026-11-08"),
    School("Maltepe University", "https://blackboard.maltepe.edu.tr", "maltepe.edu.tr", "TR",
           ("Maltepe Üniversitesi",), ("MAU",), "2026-11-08"),
    School("MEF University", "https://mef.blackboard.com", "mef.edu.tr", "TR",
           ("MEF Üniversitesi",), ("MEF",), "2026-11-08"),
    # US
    School("Baylor College of Medicine", "https://bcm.blackboard.com", "bcm.edu", "US",
           (), ("BCM",), "2026-11-08"),
    School("Boston University", "https://learn.bu.edu", "bu.edu", "US",
           (), ("BU",), "2026-11-08"),
    School("Bowie State University", "https://bsuonline.blackboard.com", "bowiestate.edu", "US",
           (), ("BSU",), "2026-11-08"),
    School("Central Michigan University", "https://blackboard.cmich.edu", "cmich.edu", "US",
           (), ("CMU",), "2026-11-08"),
    School("Drexel University", "https://learn.dcollege.net", "dcollege.net", "US",
           (), ("DREXEL", "drexel.edu"), "2026-11-08"),
    School("Fordham University", "https://fordham.blackboard.com", "fordham.edu", "US",
           (), ("FORDHAM",), "2026-11-08"),
    School("George Washington University", "https://blackboard.gwu.edu", "gwu.edu", "US",
           (), ("GW", "GWU"), "2026-11-08"),
    School("Lamar University", "https://luonline.blackboard.com", "lamar.edu", "US",
           (), ("LU",), "2026-11-08"),
    School("Northern Illinois University", "https://webcourses.niu.edu", "niu.edu", "US",
           (), ("NIU",), "2026-11-08"),
    School("Sam Houston State University", "https://shsu.blackboard.com", "shsu.edu", "US",
           (), ("SHSU",), "2026-11-08"),
    School("Syracuse University", "https://blackboard.syr.edu", "syr.edu", "US",
           (), ("SYR", "SYRACUSE"), "2026-11-08"),
    School("Towson University", "https://blackboard.towson.edu", "towson.edu", "US",
           (), ("TU",), "2026-11-08"),
    School("University of Arkansas", "https://learn.uark.edu", "uark.edu", "US",
           (), ("UARK",), "2026-11-08"),
    School("University of Arkansas at Little Rock", "https://blackboard.ualr.edu", "ualr.edu", "US",
           (), ("UA Little Rock", "UALR"), "2026-11-08"),
    School("University of Illinois Chicago", "https://uic.blackboard.com", "uic.edu", "US",
           (), ("UIC",), "2026-11-08"),
    School("University of Louisville", "https://blackboard.louisville.edu", "louisville.edu", "US",
           (), ("UofL",), "2026-11-08"),
    School("University of Maryland, Baltimore County", "https://blackboard.umbc.edu", "umbc.edu", "US",
           (), ("UMBC",), "2026-11-08"),
    School("University of Mississippi", "https://blackboard.olemiss.edu", "olemiss.edu", "US",
           (), ("Ole Miss", "UM"), "2026-11-08"),
    School("University of Richmond", "https://blackboard.richmond.edu", "richmond.edu", "US",
           (), ("URICHMOND",), "2026-11-08"),
    School("University of Rochester", "https://learn.rochester.edu", "rochester.edu", "US",
           (), ("UR", "UofR"), "2026-11-08"),
    School("University of South Carolina", "https://blackboard.sc.edu", "sc.edu", "US",
           (), ("USC", "UofSC"), "2026-11-08"),
    School("University of Toledo", "https://blackboard.utdl.edu", "utdl.edu", "US",
           (), ("UToledo", "utoledo.edu"), "2026-11-08"),
    School("Youngstown State University", "https://ysu.blackboard.com", "ysu.edu", "US",
           (), ("YSU",), "2026-11-08"),
    # ZA
    School("Cape Peninsula University of Technology", "https://myclassroom.cput.ac.za", "cput.ac.za", "ZA",
           (), ("CPUT",), "2026-11-08"),
    School("Central University of Technology", "https://ethuto.cut.ac.za", "cut.ac.za", "ZA",
           (), ("CUT",), "2026-11-08"),
    School("Mangosuthu University of Technology", "https://mut.blackboard.com", "mut.ac.za", "ZA",
           (), ("MUT",), "2026-11-08"),
    School("Sefako Makgatho Health Sciences University", "https://ithute.smu.ac.za", "smu.ac.za", "ZA",
           (), ("SMU",), "2026-11-08"),
    School("University of Fort Hare", "https://learn.ufh.ac.za", "ufh.ac.za", "ZA",
           (), ("UFH",), "2026-11-08"),
    School("University of Limpopo", "https://tmlearn.ul.ac.za", "ul.ac.za", "ZA",
           (), ("UL",), "2026-11-08"),
    School("University of Pretoria", "https://clickup.up.ac.za", "up.ac.za", "ZA",
           ("Universiteit van Pretoria", "Yunibesithi ya Pretoria"), ("Tuks", "ClickUP"), "2026-11-08"),
    School("University of the Free State", "https://ufs.blackboard.com", "ufs.ac.za", "ZA",
           ("Universiteit van die Vrystaat", "Yunivesithi ya Freistata"), ("UFS", "Kovsies"), "2026-11-08"),
)

# Letters that look different but are typed interchangeably (Arabic ة/ه and ى/ي, Turkish dotless ı).
_SAME_LETTER = str.maketrans({"ı": "i", "ة": "ه", "ى": "ي", "ـ": ""})


def fold(text: str) -> str:
    """Lower case, no accents or marks, one space between words: ``İstanbul`` and ``istanbul`` match.

    Arabic hamza forms of alef (أ إ آ) fold to a plain alef and the vowel marks go.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    bare = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[\W_]+", " ", bare.lower().translate(_SAME_LETTER)).strip()


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _index() -> dict[str, School]:
    index: dict[str, School] = {}
    for school in SCHOOLS:
        for key in (school.name, *school.local_names, *school.aliases, school.domain, _host(school.url)):
            index.setdefault(fold(key), school)
    return index


_INDEX = _index()


def find(text: str) -> School | None:
    """The school the student means by ``text``: its name, abbreviation, web domain or Blackboard host.

    Text with a scheme is already an address, so it names no school.
    """
    text = (text or "").strip()
    return None if not text or "://" in text else _INDEX.get(fold(text))


def resolve(text: str) -> str | None:
    """The Blackboard address of the school ``text`` names, or None when it names no known school."""
    school = find(text)
    return school.url if school else None


def suggestions() -> list[str]:
    """What a search list offers: each school once, by its English name, in ``SCHOOLS`` order.

    Local-language names are not listed, but ``find`` and ``resolve`` still match them.
    """
    return [school.name for school in SCHOOLS]
