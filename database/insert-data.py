from sqlalchemy.exc import SQLAlchemyError
from create_tables import db, Product, Category, Review, User, Address, app


def insert_sample_data():
    try:
        # Categorías
        category1 = Category(
            name="Juguetes para perros",
            description="Juguetes resistentes y divertidos para perros",
            image_url="https://via.placeholder.com/32",
        )
        category2 = Category(
            name="Accesorios para gatos",
            description="Productos para el cuidado y diversión de gatos",
            image_url="https://via.placeholder.com/32",
        )
        db.session.add_all([category1, category2])
        db.session.commit()
        print("✅ Categorías creadas.")

        # Productos
        product1 = Product(
            name="Pelota para perros",
            description="Pelota de goma ideal para juegos al aire libre.",
            price=10.99,
            category=category1.id,
            animal_type="dog",
            brand="DogFun",
            stock=50,
            images=["https://via.placeholder.com/32", "https://via.placeholder.com/32"],
            specifications={"material": "goma", "tamaño": "mediano"},
            tags=["juguetes", "perros"],
            average_rating=4.5,
        )
        product2 = Product(
            name="Rascador para gatos",
            description="Rascador con varias plataformas y postes.",
            price=45.99,
            category=category2.id,
            animal_type="cat",
            brand="CatKing",
            stock=20,
            images=["https://via.placeholder.com/32"],
            specifications={"material": "madera y sisal", "altura": "1.5m"},
            tags=["rascadores", "gatos"],
            average_rating=4.8,
        )
        db.session.add_all([product1, product2])
        db.session.commit()
        print("✅ Productos creados.")

        # Usuarios ficticios para las reseñas
        user1 = User(
            username="user1",
            email="user1@example.com",
            password="password123",
            first_name="Juan",
            last_name="Perez",
        )
        user2 = User(
            username="user2",
            email="user2@example.com",
            password="password123",
            first_name="Maria",
            last_name="Gomez",
        )
        db.session.add_all([user1, user2])
        db.session.commit()
        print("✅ Usuarios creados.")

        # Direcciones para los usuarios
        address1 = Address(
            user_id=user1.id,
            street="Calle Falsa 123",
            city="Madrid",
            state="Madrid",
            country="España",
            zip_code="28001",
            is_default=True,
        )
        address2 = Address(
            user_id=user2.id,
            street="Avenida Siempreviva 742",
            city="Barcelona",
            state="Cataluña",
            country="España",
            zip_code="08001",
            is_default=True,
        )
        db.session.add_all([address1, address2])
        db.session.commit()
        print("✅ Direcciones creadas.")

        # Reseñas
        review1 = Review(
            product_id=product1.id,
            user_id=user1.id,
            rating=5,
            title="¡Excelente juguete!",
            comment="A mi perro le encantó, es muy resistente.",
            helpful=10,
        )
        review2 = Review(
            product_id=product2.id,
            user_id=user2.id,
            rating=4,
            title="Buen rascador",
            comment="Mi gato lo usa mucho, pero la base podría ser más estable.",
            helpful=8,
        )
        db.session.add_all([review1, review2])
        db.session.commit()
        print("✅ Reseñas creadas.")

    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"❌ Error al insertar datos: {e}")


# Ejecutar la función para insertar datos de ejemplo
if __name__ == '__main__':
    with app.app_context():
        insert_sample_data()
