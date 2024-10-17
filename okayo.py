from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///okayo.db'
db = SQLAlchemy(app)

# Modèles de données
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    adresse = db.Column(db.String(200))
    code_postal = db.Column(db.String(10))
    ville = db.Column(db.String(100))

class Produit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    designation = db.Column(db.String(100), nullable=False)
    prix_unitaire_ht = db.Column(db.Float, nullable=False)
    tva_id = db.Column(db.Integer, db.ForeignKey('tva.id'), nullable=False)

class TVA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    taux = db.Column(db.Float, nullable=False)
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date)

class TotalTVAParFacture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, db.ForeignKey('facture.id'), nullable=False)
    taux_tva = db.Column(db.Float, nullable=False)
    montant_tva = db.Column(db.Float, nullable=False)
    facture = db.relationship('Facture', back_populates='totaux_tva') 

class Facture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(20), unique=True, nullable=False)
    date_facturation = db.Column(db.Date, nullable=False)
    date_echeance = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    total_ht = db.Column(db.Float, nullable=False)
    total_ttc = db.Column(db.Float, nullable=False)
    conditions_reglement = db.Column(db.String(200))
    #totaux_tva = db.relationship('TotalTVAParFacture', back_populates='facture')
    totaux_tva = db.relationship('TotalTVAParFacture', back_populates='facture', cascade="all, delete-orphan")

class LigneFacture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, db.ForeignKey('facture.id'), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    prix_unitaire_ht = db.Column(db.Float, nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    taux_tva = db.Column(db.Float, nullable=False)

# Routes de l'API

@app.route('/api/clients', methods=['GET'])
def get_clients():
    clients = Client.query.all()
    return jsonify([{'code': c.code, 'nom': c.nom, 'id' : c.id} for c in clients])

@app.route('/api/clients/<code>', methods=['GET'])
def get_client(code):
    client = Client.query.filter_by(code=code).first_or_404()
    return jsonify({
        'code': client.code,
        'nom': client.nom,
        'adresse': client.adresse,
        'code_postal': client.code_postal,
        'ville': client.ville
    })

@app.route('/api/produits', methods=['GET'])
def get_produits():
    produits = Produit.query.all()
    return jsonify([{'produit.id' : p.id, 'designation': p.designation, 'prix_unitaire_ht': p.prix_unitaire_ht} for p in produits])

@app.route('/api/tva/en-vigueur', methods=['GET'])
def get_tva_en_vigueur():
    date = request.args.get('date', datetime.now().date())
    tvas = TVA.query.filter(TVA.date_debut <= date, (TVA.date_fin >= date) | (TVA.date_fin == None)).all()
    return jsonify([{'taux': t.taux, 'date_debut' : t.date_debut, 'date_fin' : t.date_fin} for t in tvas])

@app.route('/api/factures', methods=['GET'])
def get_factures():
    factures = Facture.query.all()
    return jsonify([{'facture.id' : f.id, 'reference': f.reference, 'date_facturation': f.date_facturation, 'nom du client' : Client.query.filter_by(id=f.client_id).first_or_404().nom,\
                      'total_ht' : f.total_ht ,'total_ttc' : f.total_ttc} for f in factures])


@app.route('/api/factures/generer', methods=['POST'])
def generer_facture():
    data = request.json
    client = Client.query.filter_by(code=data['codeClient']).first_or_404()
    facture = Facture(
        id = data['id'],
        reference=f"{datetime.now().year}-{Facture.query.count() + 1:04d}",
        date_facturation=datetime.strptime(data['dateFacturation'], '%Y-%m-%d').date(),
        date_echeance=datetime.strptime(data['dateEcheance'], '%Y-%m-%d').date(),
        client_id=client.id,
        conditions_reglement=data['conditionsReglement']
    )
    
    total_ht = 0
    total_ttc = 0
    totaux_tva = {}
    
    for ligne in data['lignes']:
        produit = Produit.query.filter_by(designation=ligne['designationId']).first_or_404()
        tva = TVA.query.filter(produit.tva_id == TVA.id, TVA.date_debut <= facture.date_facturation,
                               (TVA.date_fin >= facture.date_facturation) | (TVA.date_fin == None)).first()
        ligne_facture = LigneFacture(
            facture_id=facture.id,
            produit_id=produit.id,
            designation=produit.designation,
            prix_unitaire_ht=produit.prix_unitaire_ht,
            quantite=ligne['quantite'],
            taux_tva=tva.taux
        )
        db.session.add(ligne_facture)
        
        ligne_total_ht = ligne['quantite'] * produit.prix_unitaire_ht
        #calcul du total pour chaque TVA différente
        if tva.taux not in totaux_tva:
            totaux_tva[tva.taux] = 0
        totaux_tva[tva.taux] += ligne_total_ht * (tva.taux / 100)
        total_ht += ligne_total_ht
        total_ttc += ligne_total_ht * (1 + tva.taux / 100)
    
    # Créer les entrées TotalTVAParFacture
    for taux, montant in totaux_tva.items():
        total_tva = TotalTVAParFacture(
            facture=facture,
            taux_tva=taux,
            montant_tva=montant
        )
        db.session.add(total_tva)
    

    facture.total_ht = total_ht
    facture.total_ttc = total_ttc
    
    db.session.add(facture)
    db.session.commit()
    
    return jsonify({
        'reference': facture.reference,
        'total_ht': facture.total_ht,
        'total_ttc': facture.total_ttc,
        'totaux_tva': totaux_tva,
    }), 201

# route pour récupérer une facture spécifique
@app.route('/api/factures/<reference>', methods=['GET'])
def get_facture(reference):
    facture = Facture.query.filter_by(reference=reference).first_or_404()
    lignes = LigneFacture.query.filter_by(facture_id=facture.id).all()
    
    return jsonify({
        'reference': facture.reference,
        'date_facturation': facture.date_facturation.strftime('%Y-%m-%d'),
        'date_echeance': facture.date_echeance.strftime('%Y-%m-%d'),
        'client': Client.query.get(facture.client_id).nom,
        'total_ht': facture.total_ht,
        'total_ttc': facture.total_ttc,
        'lignes': [{
            'designation': ligne.designation,
            'prix_unitaire_ht': ligne.prix_unitaire_ht,
            'quantite': ligne.quantite,
            'taux_tva': ligne.taux_tva
        } for ligne in lignes],
        'totaux_tva': [{
            'taux': total.taux_tva,
            'montant': total.montant_tva
        } for total in facture.totaux_tva]
    })

if __name__ == '__main__':
    app.app_context().push()
    db.create_all()
    # Quelques test de données 
    if not Client.query.first():
        client = Client(code="CU2203-0005", nom="Mon client SAS", adresse="45, rue du test", code_postal="75016", ville="PARIS")
        db.session.add(client)
    
    if not Produit.query.first():
        produits = [
            Produit(designation="Mon produit A", prix_unitaire_ht=50000.00, tva_id = 1),
            Produit(designation="Mon produit B", prix_unitaire_ht=3500.00, tva_id=2),
            Produit(designation="Mon produit C", prix_unitaire_ht=2000.00, tva_id=3),
            Produit(designation="Mon produit D", prix_unitaire_ht=4000.00, tva_id=3)
        ]
        db.session.add_all(produits)
    
    if not TVA.query.first():
        tvas = [
            TVA(taux=20.0, date_debut=datetime(2024, 1, 1).date()),
            TVA(taux=5.5, date_debut=datetime(2023, 1, 1).date()),
            TVA(taux=7.0, date_debut=datetime(2022, 1, 1).date()),
        ]
        db.session.add_all(tvas)

    db.session.commit()
    
    """Ne pas décommenté ces assert avant d'avoir générer au moins une facture 

    #Vérification de la création d'une facture
    assert Facture.query.count() > 0, "Aucune facture n'a été créée"

    #Vérification de la génération de la référence de facture
    facture = Facture.query.order_by(Facture.id.desc()).first()
    assert facture.reference.startswith(str(datetime.now().year)), "La référence de la facture ne commence pas par l'année en cours"
    
   

    #Vérification des calculs de TVA
    facture = Facture.query.order_by(Facture.id.desc()).first()
    lignes = LigneFacture.query.filter_by(facture_id=facture.id).all()
    total_tva_calcule = sum((ligne.prix_unitaire_ht * ligne.quantite * ligne.taux_tva / 100) for ligne in lignes)
    total_tva_facture = sum(total.montant_tva for total in facture.totaux_tva)
    assert abs(total_tva_calcule - total_tva_facture) < 0.01, "Le total TVA calculé ne correspond pas au total TVA de la facture"

    #Vérification de la création des lignes de facture
    facture = Facture.query.order_by(Facture.id.desc()).first()
    lignes = LigneFacture.query.filter_by(facture_id=facture.id).all()
    assert len(lignes) > 0, "Aucune ligne de facture n'a été créée"

    #Vérification des taux de TVA
    tva_20 = TVA.query.filter_by(taux=20.0).first()
    tva_5_5 = TVA.query.filter_by(taux=5.5).first()
    tva_7 = TVA.query.filter_by(taux=7.0).first()
    assert tva_20 and tva_5_5 and tva_7, "Les taux de TVA attendus ne sont pas tous présents dans la base de données"

    #Vérification de la création du client
    client = Client.query.filter_by(code="CU2203-0005").first()
    assert client, "Le client de test n'a pas été créé"

    #Vérification de la création des produits
    produits = Produit.query.all()
    assert len(produits) == 4, "Le nombre de produits de test créés ne correspond pas à l'attendu"

    #Vérification des conditions de règlement
    facture = Facture.query.order_by(Facture.id.desc()).first()
    assert facture.conditions_reglement == "Règlement à la livraison", "Les conditions de règlement ne correspondent pas à l'attendu"
    """

    app.run(debug=True)

    



